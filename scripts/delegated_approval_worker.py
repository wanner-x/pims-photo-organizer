"""Run one bounded delegated-approval batch and verify every moved file."""

from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path

from pims_v1.db import SessionLocal
from pims_v1.models.asset import Asset
from pims_v1.models.series import (
    Series,
    SeriesCandidate,
    SeriesCandidateAsset,
    SeriesSuggestion,
)
from pims_v1.services.archive_rule_planner import plan_archive_from_source_root
from pims_v1.services.series_confirm_service import (
    confirm_series_suggestion,
    safe_series_path_segment,
)


PIMS_DELEGATED_REVIEWED_APPROVAL_WORKER = True
ARCHIVE_ROOT = r"\\192.168.31.10\personal_folder\网络写真集"
MAX_CONFIRMED = 200
MAX_BYTES = 500 * 1024**3
BLOCKED_RISK_TERMS = (
    "疑似重复",
    "重复",
    "duplicate",
    "来源不明",
    "来源不清",
    "低置信",
    "target_conflict",
    "目标冲突",
)


def emit(event: str, **payload: object) -> None:
    row = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **payload,
    }
    print(json.dumps(row, ensure_ascii=False), flush=True)


def risk_text(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        value = json.loads(raw)
    except Exception:
        value = raw
    if isinstance(value, list):
        return " ".join(str(item) for item in value).casefold()
    return str(value).casefold()


def run() -> None:
    summary = {
        "considered": 0,
        "confirmed": 0,
        "moved": 0,
        "failed": 0,
        "verified": 0,
        "bytes": 0,
        "held_target": 0,
        "held_missing": 0,
        "held_mismatch": 0,
        "held_risk": 0,
        "held_limit": 0,
    }
    session = SessionLocal()
    try:
        suggestions = (
            session.query(SeriesSuggestion)
            .filter(
                SeriesSuggestion.status == "pending_review",
                SeriesSuggestion.confidence >= 0.9,
            )
            .order_by(SeriesSuggestion.id)
            .all()
        )
        candidates: list[tuple[int, int]] = []
        for suggestion in suggestions:
            rows = (
                session.query(SeriesCandidateAsset, Asset)
                .join(Asset, Asset.id == SeriesCandidateAsset.asset_id)
                .filter(SeriesCandidateAsset.candidate_id == suggestion.candidate_id)
                .all()
            )
            candidates.append(
                (sum(int(asset.file_size or 0) for _, asset in rows), suggestion.id)
            )
        candidates.sort()

        for total_bytes, suggestion_id in candidates:
            if summary["confirmed"] >= MAX_CONFIRMED:
                summary["held_limit"] += 1
                continue
            summary["considered"] += 1
            suggestion = session.get(SeriesSuggestion, suggestion_id)
            if suggestion is None or suggestion.status != "pending_review":
                continue
            candidate = session.get(SeriesCandidate, suggestion.candidate_id)
            if candidate is None:
                summary["held_missing"] += 1
                continue
            if any(
                term.casefold() in risk_text(suggestion.risk_flags)
                for term in BLOCKED_RISK_TERMS
            ):
                summary["held_risk"] += 1
                continue

            rule = plan_archive_from_source_root(candidate.source_root)
            rule_category = str(
                rule.get("archive_category") or rule.get("category") or ""
            )
            rule_title = str(rule.get("archive_title") or rule.get("title") or "")
            ai_category = str(suggestion.suggested_category or "")
            ai_title = str(suggestion.suggested_title or "")
            r18_allowed = bool(suggestion.r18_label) and ai_title == rule_title + " [R18]"
            if ai_category != rule_category or not (
                ai_title == rule_title or r18_allowed
            ):
                summary["held_mismatch"] += 1
                continue

            rows = (
                session.query(SeriesCandidateAsset, Asset)
                .join(Asset, Asset.id == SeriesCandidateAsset.asset_id)
                .filter(SeriesCandidateAsset.candidate_id == candidate.id)
                .order_by(SeriesCandidateAsset.sort_order, SeriesCandidateAsset.id)
                .all()
            )
            if not rows:
                summary["held_missing"] += 1
                continue
            sources: list[tuple[int, int]] = []
            for _, asset in rows:
                source = Path(asset.current_path or asset.original_path)
                if not source.is_file():
                    break
                sources.append((asset.id, int(asset.file_size or 0)))
            if len(sources) != len(rows):
                summary["held_missing"] += 1
                continue

            target = (
                Path(ARCHIVE_ROOT)
                / safe_series_path_segment(ai_category)
                / safe_series_path_segment(ai_title)
            )
            target_in_db = (
                session.query(Series.id)
                .filter(Series.archive_path == str(target))
                .first()
                is not None
            )
            if target.exists() or target_in_db:
                summary["held_target"] += 1
                continue
            if summary["bytes"] + total_bytes > MAX_BYTES:
                summary["held_limit"] += 1
                continue

            emit(
                "candidate_start",
                suggestion_id=suggestion.id,
                assets=len(rows),
                bytes=total_bytes,
                target=str(target),
                r18=r18_allowed,
            )
            result = confirm_series_suggestion(
                session=session,
                suggestion_id=suggestion.id,
                archive_root=ARCHIVE_ROOT,
                title=ai_title,
                category=ai_category,
            )
            session.expire_all()
            failed = int(result.get("failed", 0))
            moved = int(result.get("moved", 0))
            if failed or result.get("status") != "confirmed" or moved != len(rows):
                summary["failed"] += max(1, failed)
                emit(
                    "fatal_failure",
                    suggestion_id=suggestion.id,
                    reason="confirm_result",
                    result=result,
                    expected=len(rows),
                    summary=summary,
                )
                break

            verified = 0
            verification_error = None
            for asset_id, expected_size in sources:
                asset = session.get(Asset, asset_id)
                destination = Path(asset.current_path or "")
                if not destination.is_file():
                    verification_error = (
                        f"target_missing asset={asset_id} path={destination}"
                    )
                    break
                actual_size = destination.stat().st_size
                if actual_size != expected_size:
                    verification_error = (
                        f"size_mismatch asset={asset_id} expected={expected_size} "
                        f"actual={actual_size} path={destination}"
                    )
                    break
                verified += 1
            if verification_error:
                summary["failed"] += 1
                emit(
                    "fatal_failure",
                    suggestion_id=suggestion.id,
                    reason=verification_error,
                    moved=moved,
                    verified=verified,
                    summary=summary,
                )
                break

            summary["confirmed"] += 1
            summary["moved"] += moved
            summary["verified"] += verified
            summary["bytes"] += total_bytes
            emit(
                "candidate_complete",
                suggestion_id=suggestion.id,
                assets=len(rows),
                bytes=total_bytes,
                moved=moved,
                failed=0,
                verified=verified,
                r18=r18_allowed,
                target=str(target),
                summary=summary,
            )
        emit("worker_complete", summary=summary)
    except Exception as exc:
        session.rollback()
        summary["failed"] += 1
        emit(
            "fatal_exception",
            error=repr(exc),
            traceback=traceback.format_exc(),
            summary=summary,
        )
    finally:
        session.close()


if __name__ == "__main__":
    run()
