from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy.orm import Session

from pims_v1.models.archive_decision import (
    ArchiveExecutionRecord,
    ArchivePlanningRecord,
    ArchiveRiskEvent,
    ArchiveRollbackRecord,
)
from pims_v1.models.asset import Asset
from pims_v1.models.series import Series, SeriesAsset, SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.services.ai_naming_service import (
    NamingClient,
    _candidate_sample_file_names,
    _existing_archive_dirs,
    generate_ai_archive_plan,
)
from pims_v1.services.archive_rule_planner import plan_archive_from_source_root
from pims_v1.services.series_moderation_service import latest_series_moderation_summary
from pims_v1.services.series_confirm_service import _unique_archive_dir, _unique_file_path


def _json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _persisted_suggestion_ai_plan(
    *,
    session: Session,
    candidate_id: int,
) -> dict[str, object] | None:
    suggestion = (
        session.query(SeriesSuggestion)
        .filter(
            SeriesSuggestion.candidate_id == candidate_id,
            SeriesSuggestion.status == "pending_review",
        )
        .one_or_none()
    )
    if suggestion is None or not suggestion.suggested_title or not suggestion.suggested_category:
        return None
    return {
        "title": suggestion.suggested_title,
        "category": suggestion.suggested_category,
        "archive_path": suggestion.suggested_archive_path or "",
        "plan_summary": suggestion.plan_summary or "",
        "risk_flags": _json_list(suggestion.risk_flags),
        "tags": _json_list(suggestion.content_tags),
        "r18_label": bool(suggestion.r18_label),
        "r18_confidence": float(suggestion.r18_confidence or 0.0),
        "r18_reason": suggestion.r18_reason or "",
        "confidence": float(suggestion.confidence or 0.0),
        "raw_response": suggestion.raw_response or "",
    }


def merge_archive_plans(
    *,
    rule_plan: dict[str, object],
    ai_plan: dict[str, object],
    moderation_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    rule_score = float(rule_plan.get("confidence", 0.0))
    ai_score = float(ai_plan.get("confidence", 0.0))
    risk_flags = {
        str(flag)
        for flag in [*list(rule_plan.get("risk_flags", [])), *list(ai_plan.get("risk_flags", []))]
        if str(flag).strip()
    }
    if bool(ai_plan.get("r18_label", False)):
        risk_flags.add("r18_suspected")
    if moderation_summary:
        if bool(moderation_summary.get("r18_label", False)):
            risk_flags.add("visual_r18_suspected")
        for risk_flag in moderation_summary.get("risk_flags", []):
            text = str(risk_flag).strip()
            if text:
                risk_flags.add(text)

    same_category = rule_plan.get("category") == ai_plan.get("category")
    same_title = rule_plan.get("title") == ai_plan.get("title")

    if risk_flags:
        decision_type = "manual_review"
        final_category = str(ai_plan.get("category") or rule_plan.get("category") or "未分类")
        final_title = str(ai_plan.get("title") or rule_plan.get("title") or "Untitled Series")
    elif same_category and same_title:
        decision_type = "auto_apply"
        final_category = str(rule_plan["category"])
        final_title = str(rule_plan["title"])
    elif same_category and rule_score >= 0.9 and ai_score >= 0.8:
        decision_type = "auto_apply_sampled"
        final_category = str(rule_plan["category"])
        final_title = str(rule_plan["title"])
        risk_flags.add("sample_review_recommended")
    else:
        decision_type = "manual_review"
        final_category = str(rule_plan.get("category") or ai_plan.get("category") or "未分类")
        final_title = str(rule_plan.get("title") or ai_plan.get("title") or "Untitled Series")
        risk_flags.add("planner_disagreement")

    risk_score = (
        1.0
        if any(flag.startswith("r18") or flag.startswith("visual_r18") for flag in risk_flags)
        else min(1.0, len(risk_flags) * 0.25)
    )
    r18_label = bool(ai_plan.get("r18_label", False)) or bool(moderation_summary and moderation_summary.get("r18_label", False))
    r18_confidence = max(
        float(ai_plan.get("r18_confidence", 0.0)),
        float(moderation_summary.get("r18_confidence", 0.0)) if moderation_summary else 0.0,
    )
    r18_reason = str(
        ai_plan.get("r18_reason")
        or (moderation_summary.get("r18_reason") if moderation_summary else "")
        or ""
    )
    tags = list(ai_plan.get("tags", []))
    if r18_label and "R18" not in tags:
        tags.insert(0, "R18")
    return {
        "decision_type": decision_type,
        "rule_score": rule_score,
        "ai_score": ai_score,
        "risk_score": risk_score,
        "category": final_category,
        "title": final_title,
        "plan_summary": str(ai_plan.get("plan_summary", "")),
        "risk_flags": sorted(risk_flags),
        "tags": tags,
        "r18_label": r18_label,
        "r18_confidence": r18_confidence,
        "r18_reason": r18_reason,
        "decision_reason": (
            f"decision={decision_type}; rule={rule_plan.get('category')}/{rule_plan.get('title')}; "
            f"ai={ai_plan.get('category')}/{ai_plan.get('title')}; risk_flags={sorted(risk_flags)}"
        ),
    }


def _persist_planning_record(
    *,
    session: Session,
    candidate: SeriesCandidate,
    rule_plan: dict[str, object],
    ai_plan: dict[str, object],
    merged: dict[str, object],
) -> ArchivePlanningRecord:
    planning_record = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json=json.dumps(rule_plan, ensure_ascii=False),
        ai_plan_json=json.dumps(ai_plan, ensure_ascii=False),
        final_plan_json=json.dumps(merged, ensure_ascii=False),
        decision_type=str(merged["decision_type"]),
        rule_score=float(merged["rule_score"]),
        ai_score=float(merged["ai_score"]),
        risk_score=float(merged["risk_score"]),
        decision_reason=str(merged["decision_reason"]),
    )
    session.add(planning_record)
    session.flush()
    return planning_record


def _create_risk_events(
    *,
    session: Session,
    planning_record: ArchivePlanningRecord,
    merged: dict[str, object],
) -> int:
    risk_flags = list(merged.get("risk_flags", []))
    for risk_flag in risk_flags:
        session.add(
            ArchiveRiskEvent(
                planning_record_id=planning_record.id,
                event_type=str(risk_flag),
                severity="warning",
                details_json=json.dumps(
                    {"decision_reason": merged["decision_reason"], "title": merged["title"]},
                    ensure_ascii=False,
                ),
            )
        )
    return len(risk_flags)


def _execute_archive_move(
    *,
    session: Session,
    candidate: SeriesCandidate,
    planning_record: ArchivePlanningRecord,
    merged: dict[str, object],
    archive_root: str,
) -> dict[str, object]:
    archive_dir = _unique_archive_dir(
        session,
        archive_root,
        str(merged["category"]),
        str(merged["title"]),
    )
    archive_dir.mkdir(parents=True, exist_ok=True)
    series = Series(
        library_id=candidate.library_id,
        title=str(merged["title"]),
        archive_path=str(archive_dir),
        status="confirmed",
    )
    session.add(series)
    session.flush()

    rows = (
        session.query(SeriesCandidateAsset)
        .filter(SeriesCandidateAsset.candidate_id == candidate.id)
        .order_by(SeriesCandidateAsset.sort_order, SeriesCandidateAsset.id)
        .all()
    )
    moved = 0
    failed = 0
    execution_ids: list[int] = []
    for row in rows:
        asset = session.get(Asset, row.asset_id)
        if asset is None:
            failed += 1
            continue
        source = Path(asset.current_path or asset.original_path)
        destination = _unique_file_path(archive_dir, asset.file_name or source.name)
        execution = ArchiveExecutionRecord(
            planning_record_id=planning_record.id,
            operation_type="archive_move",
            source_path=str(source),
            target_path=str(destination),
            status="pending",
            started_at=datetime.now(UTC),
        )
        session.add(execution)
        session.flush()
        execution_ids.append(execution.id)
        try:
            if source.resolve() != destination.resolve():
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.rename(destination)
            asset.current_path = str(destination)
            asset.status = "archived"
            session.add(
                SeriesAsset(
                    series_id=series.id,
                    asset_id=asset.id,
                    sort_order=row.sort_order,
                )
            )
            execution.status = "done"
            execution.finished_at = datetime.now(UTC)
            moved += 1
        except Exception as exc:
            execution.status = "failed"
            execution.finished_at = datetime.now(UTC)
            execution.error_message = str(exc)
            failed += 1

    candidate.title = str(merged["title"])
    candidate.status = "confirmed" if failed == 0 else "failed"
    candidate.confidence = max(float(merged["rule_score"]), float(merged["ai_score"]))
    series.status = "confirmed" if failed == 0 else "failed"
    suggestion = (
        session.query(SeriesSuggestion)
        .filter(
            SeriesSuggestion.candidate_id == candidate.id,
            SeriesSuggestion.status == "pending_review",
        )
        .one_or_none()
    )
    if suggestion is not None:
        suggestion.status = candidate.status
    session.commit()
    return {
        "candidate_id": candidate.id,
        "series_id": series.id,
        "archive_path": str(archive_dir),
        "decision_type": merged["decision_type"],
        "status": candidate.status,
        "moved": moved,
        "risk_events": 0,
        "execution_ids": execution_ids,
    }


def rollback_archive_execution(
    *,
    session: Session,
    execution_id: int,
    operator: str | None = None,
) -> dict[str, object]:
    execution = session.get(ArchiveExecutionRecord, execution_id)
    if execution is None:
        raise ValueError(f"Archive execution record not found: {execution_id}")
    if execution.status != "done":
        raise ValueError(f"Archive execution is not completed: {execution.status}")
    if not execution.target_path:
        raise ValueError(f"Archive execution target path is missing: {execution_id}")

    asset = session.query(Asset).filter(Asset.current_path == execution.target_path).one_or_none()
    if asset is None:
        raise ValueError(f"Archived asset not found for execution: {execution_id}")

    source = Path(execution.target_path)
    destination = Path(execution.source_path)
    if not source.exists():
        raise ValueError(f"Archived file is missing for execution: {execution_id}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    asset.current_path = str(destination)
    asset.status = "normal"
    execution.status = "rolled_back"
    execution.finished_at = datetime.now(UTC)
    session.add(
        ArchiveRollbackRecord(
            execution_record_id=execution.id,
            rollback_source_path=str(source),
            rollback_target_path=str(destination),
            status="done",
            operator=operator,
        )
    )
    session.commit()
    return {
        "execution_id": execution.id,
        "asset_id": asset.id,
        "status": execution.status,
        "source_path": execution.source_path,
        "target_path": execution.target_path,
    }


def auto_archive_candidates(
    *,
    session: Session,
    archive_root: str,
    client: NamingClient,
    limit: int = 20,
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
        "auto_apply": 0,
        "auto_apply_sampled": 0,
        "manual_review": 0,
        "confirmed": 0,
        "pending_review": 0,
        "failed": 0,
        "moved": 0,
        "risk_events": 0,
    }
    for candidate_id in candidate_ids:
        try:
            result = auto_archive_candidate(
                session=session,
                candidate_id=candidate_id,
                archive_root=archive_root,
                client=client,
            )
        except Exception:
            session.rollback()
            summary["failed"] += 1
            continue
        summary["processed"] += 1
        decision_type = str(result.get("decision_type", ""))
        status = str(result.get("status", ""))
        if decision_type in summary:
            summary[decision_type] += 1
        if status in summary:
            summary[status] += 1
        summary["moved"] += int(result.get("moved", 0))
        summary["risk_events"] += int(result.get("risk_events", 0))
    return summary


def auto_archive_candidate(
    *,
    session: Session,
    candidate_id: int,
    archive_root: str,
    client: NamingClient,
) -> dict[str, object]:
    candidate = session.get(SeriesCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {candidate_id}")

    rule_plan = plan_archive_from_source_root(candidate.source_root)
    ai_plan = _persisted_suggestion_ai_plan(session=session, candidate_id=candidate_id)
    if ai_plan is None:
        ai_plan = generate_ai_archive_plan(
            source_root=candidate.source_root,
            file_names=_candidate_sample_file_names(session, candidate_id),
            archive_root=archive_root,
            existing_archive_dirs=_existing_archive_dirs(session, archive_root),
            client=client,
        )
    moderation_summary = latest_series_moderation_summary(session, candidate_id)
    merged = merge_archive_plans(
        rule_plan=rule_plan,
        ai_plan=ai_plan,
        moderation_summary=moderation_summary,
    )
    planning_record = _persist_planning_record(
        session=session,
        candidate=candidate,
        rule_plan=rule_plan,
        ai_plan=ai_plan,
        merged=merged,
    )

    if str(merged["decision_type"]) not in {"auto_apply", "auto_apply_sampled"}:
        candidate.status = "pending_review"
        candidate.confidence = max(float(merged["rule_score"]), float(merged["ai_score"]))
        risk_event_count = _create_risk_events(session=session, planning_record=planning_record, merged=merged)
        session.commit()
        return {
            "candidate_id": candidate.id,
            "decision_type": merged["decision_type"],
            "status": "pending_review",
            "moved": 0,
            "risk_events": risk_event_count,
        }

    result = _execute_archive_move(
        session=session,
        candidate=candidate,
        planning_record=planning_record,
        merged=merged,
        archive_root=archive_root,
    )
    if str(merged["decision_type"]) == "auto_apply_sampled":
        result["risk_events"] = _create_risk_events(
            session=session,
            planning_record=planning_record,
            merged=merged,
        )
        session.commit()
    return result
