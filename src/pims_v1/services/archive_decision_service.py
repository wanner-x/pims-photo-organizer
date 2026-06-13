from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy.orm import Session

from pims_v1.models.archive_decision import (
    ArchiveExecutionRecord,
    ArchivePlanningRecord,
    ArchiveRiskEvent,
)
from pims_v1.models.asset import Asset
from pims_v1.models.series import Series, SeriesAsset, SeriesCandidate, SeriesCandidateAsset
from pims_v1.services.ai_naming_service import (
    NamingClient,
    _candidate_sample_file_names,
    _existing_archive_dirs,
    generate_ai_archive_plan,
)
from pims_v1.services.archive_rule_planner import plan_archive_from_source_root
from pims_v1.services.series_confirm_service import _unique_archive_dir, _unique_file_path


def merge_archive_plans(*, rule_plan: dict[str, object], ai_plan: dict[str, object]) -> dict[str, object]:
    rule_score = float(rule_plan.get("confidence", 0.0))
    ai_score = float(ai_plan.get("confidence", 0.0))
    risk_flags = {
        str(flag)
        for flag in [*list(rule_plan.get("risk_flags", [])), *list(ai_plan.get("risk_flags", []))]
        if str(flag).strip()
    }
    if bool(ai_plan.get("r18_label", False)):
        risk_flags.add("r18_suspected")

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

    risk_score = 1.0 if any(flag.startswith("r18") for flag in risk_flags) else min(1.0, len(risk_flags) * 0.25)
    return {
        "decision_type": decision_type,
        "rule_score": rule_score,
        "ai_score": ai_score,
        "risk_score": risk_score,
        "category": final_category,
        "title": final_title,
        "plan_summary": str(ai_plan.get("plan_summary", "")),
        "risk_flags": sorted(risk_flags),
        "tags": list(ai_plan.get("tags", [])),
        "r18_label": bool(ai_plan.get("r18_label", False)),
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
    session.commit()
    return {
        "candidate_id": candidate.id,
        "series_id": series.id,
        "archive_path": str(archive_dir),
        "decision_type": merged["decision_type"],
        "status": candidate.status,
        "moved": moved,
        "risk_events": 0,
    }


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
    ai_plan = generate_ai_archive_plan(
        source_root=candidate.source_root,
        file_names=_candidate_sample_file_names(session, candidate_id),
        archive_root=archive_root,
        existing_archive_dirs=_existing_archive_dirs(session, archive_root),
        client=client,
    )
    merged = merge_archive_plans(rule_plan=rule_plan, ai_plan=ai_plan)
    planning_record = _persist_planning_record(
        session=session,
        candidate=candidate,
        rule_plan=rule_plan,
        ai_plan=ai_plan,
        merged=merged,
    )

    if str(merged["decision_type"]) != "auto_apply":
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

    return _execute_archive_move(
        session=session,
        candidate=candidate,
        planning_record=planning_record,
        merged=merged,
        archive_root=archive_root,
    )
