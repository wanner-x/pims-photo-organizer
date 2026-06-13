from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.models.series_moderation import SeriesModerationRun, SeriesModerationSample
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES
from pims_v1.services.visual_moderation_service import VisualModerationClient


@dataclass(frozen=True)
class CandidateImageSample:
    asset_id: int
    sort_order: int
    path: Path
    file_name: str
    file_ext: str


def select_candidate_image_samples(
    *,
    session: Session,
    candidate_id: int,
    limit: int,
) -> list[CandidateImageSample]:
    rows = (
        session.query(SeriesCandidateAsset, Asset)
        .join(Asset, Asset.id == SeriesCandidateAsset.asset_id)
        .filter(SeriesCandidateAsset.candidate_id == candidate_id)
        .filter(Asset.file_ext.in_(sorted(IMAGE_SUFFIXES)))
        .order_by(SeriesCandidateAsset.sort_order, Asset.id)
        .all()
    )
    samples = [
        CandidateImageSample(
            asset_id=asset_row.id,
            sort_order=candidate_asset.sort_order,
            path=Path(asset_row.current_path or asset_row.original_path),
            file_name=asset_row.file_name or Path(asset_row.original_path).name,
            file_ext=asset_row.file_ext or Path(asset_row.original_path).suffix,
        )
        for candidate_asset, asset_row in rows
    ]
    if len(samples) <= limit:
        return samples
    indexes = {round(index * (len(samples) - 1) / (limit - 1)) for index in range(limit)}
    ordered_indexes = sorted(indexes)
    selected = [samples[index] for index in ordered_indexes]
    cursor = 0
    while len(selected) < limit and cursor < len(samples):
        candidate = samples[cursor]
        if candidate not in selected:
            selected.append(candidate)
        cursor += 1
    return sorted(selected, key=lambda sample: sample.sort_order)


def review_series_r18(
    *,
    session: Session,
    candidate_id: int,
    provider: VisualModerationClient,
    mode: str,
    sample_limit: int,
    high_threshold: float,
    review_threshold: float,
) -> dict[str, object]:
    candidate = session.get(SeriesCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {candidate_id}")

    sampled_assets = select_candidate_image_samples(session=session, candidate_id=candidate_id, limit=sample_limit)
    sample_results: list[dict[str, object]] = []
    positive_samples = 0
    review_hits = 0
    max_score = 0.0
    run_status = "completed"

    if not sampled_assets:
        run_status = "completed_with_errors"

    run_row = SeriesModerationRun(
        candidate_id=candidate_id,
        provider=getattr(provider, "provider_name", "unknown"),
        mode=mode,
        status=run_status,
        total_samples=len(sampled_assets),
    )
    session.add(run_row)
    session.flush()

    for sample in sampled_assets:
        try:
            result = provider.moderate_image(sample.path)
        except Exception as exc:
            run_status = "completed_with_errors"
            result = {
                "label": "error",
                "score": 0.0,
                "reason": str(exc),
                "provider": getattr(provider, "provider_name", "unknown"),
            }
        score = float(result.get("score", 0.0))
        max_score = max(max_score, score)
        if score >= high_threshold:
            positive_samples += 1
        elif score >= review_threshold:
            review_hits += 1
        sample_results.append(result)
        session.add(
            SeriesModerationSample(
                run_id=run_row.id,
                asset_id=sample.asset_id,
                sample_path=str(sample.path),
                media_kind="image",
                sample_status="completed" if result.get("label") != "error" else "failed",
                label=str(result.get("label", "safe")),
                score=score,
                reason=str(result.get("reason", "")),
                provider_json=json.dumps(result, ensure_ascii=False),
            )
        )

    risk_flags: list[str] = []
    if not sampled_assets:
        risk_flags.append("visual_scan_incomplete")
        reason = "no supported image samples"
    elif positive_samples > 0:
        risk_flags.append("visual_r18_suspected")
        reason = f"visual provider {run_row.provider} flagged {positive_samples} samples"
    elif review_hits > 0:
        risk_flags.append("visual_review_required")
        reason = f"visual provider {run_row.provider} found borderline samples"
    else:
        reason = f"visual provider {run_row.provider} found no high-risk samples"

    summary = {
        "candidate_id": candidate_id,
        "provider": run_row.provider,
        "mode": mode,
        "r18_label": positive_samples > 0,
        "r18_confidence": max_score,
        "r18_reason": reason,
        "risk_flags": risk_flags,
        "sample_count": len(sampled_assets),
        "positive_samples": positive_samples,
    }
    run_row.status = run_status
    run_row.flagged_samples = positive_samples
    run_row.max_score = max_score
    run_row.summary_json = json.dumps(summary, ensure_ascii=False)
    suggestion = (
        session.query(SeriesSuggestion)
        .filter(SeriesSuggestion.candidate_id == candidate_id)
        .one_or_none()
    )
    if suggestion is not None:
        tags = json.loads(suggestion.content_tags or "[]")
        if summary["r18_label"] and "R18" not in tags:
            tags.insert(0, "R18")
        suggestion.content_tags = json.dumps(tags, ensure_ascii=False)
        suggestion.r18_label = bool(summary["r18_label"])
        suggestion.r18_confidence = float(summary["r18_confidence"])
        suggestion.r18_reason = str(summary["r18_reason"])
    session.commit()
    return summary


def review_series_r18_candidates(
    *,
    session: Session,
    provider: VisualModerationClient,
    mode: str,
    limit: int,
    sample_limit: int,
    high_threshold: float,
    review_threshold: float,
    candidate_statuses: tuple[str, ...] = ("pending", "ai_suggested"),
) -> dict[str, int]:
    candidate_ids = [
        row[0]
        for row in (
            session.query(SeriesCandidate.id)
            .filter(SeriesCandidate.status.in_(candidate_statuses))
            .order_by(SeriesCandidate.id)
            .limit(limit)
            .all()
        )
    ]
    summary = {
        "considered": len(candidate_ids),
        "processed": 0,
        "flagged": 0,
        "review_required": 0,
        "incomplete": 0,
        "failed": 0,
    }
    for candidate_id in candidate_ids:
        try:
            result = review_series_r18(
                session=session,
                candidate_id=candidate_id,
                provider=provider,
                mode=mode,
                sample_limit=sample_limit,
                high_threshold=high_threshold,
                review_threshold=review_threshold,
            )
        except Exception:
            session.rollback()
            summary["failed"] += 1
            continue
        summary["processed"] += 1
        risk_flags = set(result.get("risk_flags", []))
        if result.get("r18_label"):
            summary["flagged"] += 1
        if "visual_review_required" in risk_flags:
            summary["review_required"] += 1
        if "visual_scan_incomplete" in risk_flags:
            summary["incomplete"] += 1
    return summary


def latest_series_moderation_summary(session: Session, candidate_id: int) -> dict[str, object] | None:
    run_row = (
        session.query(SeriesModerationRun)
        .filter(SeriesModerationRun.candidate_id == candidate_id)
        .order_by(SeriesModerationRun.id.desc())
        .first()
    )
    if run_row is None:
        return None
    summary = json.loads(run_row.summary_json or "{}")
    summary.setdefault("provider", run_row.provider)
    summary.setdefault("mode", run_row.mode)
    summary.setdefault("status", run_row.status)
    summary.setdefault("sample_count", run_row.total_samples)
    summary.setdefault("positive_samples", run_row.flagged_samples)
    return summary
