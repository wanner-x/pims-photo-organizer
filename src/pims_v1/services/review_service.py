import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.archive_decision import ArchiveExecutionRecord, ArchivePlanningRecord, ArchiveRiskEvent
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.similar import SimilarGroup, SimilarGroupAsset
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion


def list_series_candidates(session: Session, limit: int = 20) -> list[dict]:
    rows = (
        session.query(
            SeriesCandidate.id,
            SeriesCandidate.title,
            SeriesCandidate.source_root,
            SeriesCandidate.status,
            func.count(SeriesCandidateAsset.asset_id).label("asset_count"),
        )
        .outerjoin(
            SeriesCandidateAsset,
            SeriesCandidateAsset.candidate_id == SeriesCandidate.id,
        )
        .group_by(
            SeriesCandidate.id,
            SeriesCandidate.title,
            SeriesCandidate.source_root,
            SeriesCandidate.status,
        )
        .order_by(SeriesCandidate.id)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "title": row.title,
            "source_root": row.source_root,
            "asset_count": row.asset_count,
            "status": row.status,
        }
        for row in rows
    ]


def _series_asset_payload(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "file_name": asset.file_name,
        "current_path": asset.current_path or asset.original_path,
        "file_ext": asset.file_ext,
        "file_size": asset.file_size,
        "thumbnail_url": f"/thumbnails/{asset.id}.jpg",
        "media_url": f"/media/assets/{asset.id}",
    }


def list_series_review_candidates(
    session: Session,
    limit: int = 20,
    status: str | None = None,
    asset_limit: int = 8,
) -> list[dict]:
    query = session.query(SeriesCandidate).order_by(SeriesCandidate.id)
    if status:
        query = query.filter(SeriesCandidate.status == status)
    else:
        query = query.filter(SeriesCandidate.status.notin_(("confirmed",)))
    candidates = query.limit(limit).all()
    result = []
    for candidate in candidates:
        asset_rows = (
            session.query(Asset)
            .join(SeriesCandidateAsset, SeriesCandidateAsset.asset_id == Asset.id)
            .filter(SeriesCandidateAsset.candidate_id == candidate.id)
            .order_by(SeriesCandidateAsset.sort_order, Asset.id)
            .all()
        )
        suggestion = (
            session.query(SeriesSuggestion)
            .filter(SeriesSuggestion.candidate_id == candidate.id)
            .one_or_none()
        )
        result.append(
            {
                "id": candidate.id,
                "title": candidate.title,
                "source_root": candidate.source_root,
                "asset_count": len(asset_rows),
                "status": candidate.status,
                "suggestion": None
                if suggestion is None
                else {
                    "id": suggestion.id,
                    "title": suggestion.suggested_title,
                    "category": suggestion.suggested_category,
                    "archive_path": suggestion.suggested_archive_path,
                    "plan_summary": suggestion.plan_summary,
                    "risk_flags": json.loads(suggestion.risk_flags or "[]"),
                    "tags": json.loads(suggestion.content_tags or "[]"),
                    "r18_label": suggestion.r18_label,
                    "r18_confidence": suggestion.r18_confidence,
                    "r18_reason": suggestion.r18_reason,
                    "confidence": suggestion.confidence,
                    "status": suggestion.status,
                },
                "assets": [_series_asset_payload(asset) for asset in asset_rows[:asset_limit]],
            }
        )
    return result


def get_archive_review_overview(session: Session) -> dict[str, dict[str, int] | int]:
    planning_rows = (
        session.query(
            ArchivePlanningRecord.decision_type,
            func.count(ArchivePlanningRecord.id),
        )
        .group_by(ArchivePlanningRecord.decision_type)
        .all()
    )
    execution_rows = (
        session.query(
            ArchiveExecutionRecord.status,
            func.count(ArchiveExecutionRecord.id),
        )
        .group_by(ArchiveExecutionRecord.status)
        .all()
    )
    return {
        "planning": {str(decision_type): count for decision_type, count in planning_rows},
        "executions": {str(status): count for status, count in execution_rows},
        "risk_events": session.query(ArchiveRiskEvent).count(),
    }


def list_archive_anomalies(session: Session, limit: int = 20) -> list[dict]:
    rows = (
        session.query(ArchiveRiskEvent, ArchivePlanningRecord, SeriesCandidate)
        .join(ArchivePlanningRecord, ArchivePlanningRecord.id == ArchiveRiskEvent.planning_record_id)
        .join(SeriesCandidate, SeriesCandidate.id == ArchivePlanningRecord.candidate_id)
        .order_by(ArchiveRiskEvent.id.desc())
        .limit(limit)
        .all()
    )
    result = []
    for risk_event, planning_record, candidate in rows:
        result.append(
            {
                "id": risk_event.id,
                "event_type": risk_event.event_type,
                "severity": risk_event.severity,
                "details": json.loads(risk_event.details_json or "{}"),
                "decision_type": planning_record.decision_type,
                "decision_reason": planning_record.decision_reason,
                "candidate": {
                    "id": candidate.id,
                    "title": candidate.title,
                    "source_root": candidate.source_root,
                    "status": candidate.status,
                },
            }
        )
    return result


def list_archive_execution_ledger(session: Session, limit: int = 20) -> list[dict]:
    rows = (
        session.query(ArchiveExecutionRecord, ArchivePlanningRecord, SeriesCandidate)
        .join(ArchivePlanningRecord, ArchivePlanningRecord.id == ArchiveExecutionRecord.planning_record_id)
        .join(SeriesCandidate, SeriesCandidate.id == ArchivePlanningRecord.candidate_id)
        .order_by(ArchiveExecutionRecord.id.desc())
        .limit(limit)
        .all()
    )
    result = []
    for execution, planning_record, candidate in rows:
        result.append(
            {
                "id": execution.id,
                "candidate_id": candidate.id,
                "candidate_title": candidate.title,
                "source_root": candidate.source_root,
                "decision_type": planning_record.decision_type,
                "decision_reason": planning_record.decision_reason,
                "operation_type": execution.operation_type,
                "source_path": execution.source_path,
                "target_path": execution.target_path,
                "status": execution.status,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
                "error_message": execution.error_message,
            }
        )
    return result


def list_archive_sampling_queue(session: Session, limit: int = 20) -> list[dict]:
    rows = (
        session.query(ArchivePlanningRecord, SeriesCandidate)
        .join(SeriesCandidate, SeriesCandidate.id == ArchivePlanningRecord.candidate_id)
        .filter(ArchivePlanningRecord.decision_type == "auto_apply_sampled")
        .order_by(ArchivePlanningRecord.id.desc())
        .limit(limit)
        .all()
    )
    result = []
    for planning_record, candidate in rows:
        result.append(
            {
                "id": planning_record.id,
                "decision_type": planning_record.decision_type,
                "decision_reason": planning_record.decision_reason,
                "rule_score": planning_record.rule_score,
                "ai_score": planning_record.ai_score,
                "risk_score": planning_record.risk_score,
                "candidate": {
                    "id": candidate.id,
                    "title": candidate.title,
                    "source_root": candidate.source_root,
                    "status": candidate.status,
                },
            }
        )
    return result


def _asset_payload(asset: Asset, thumbnail_base: str) -> dict:
    return {
        "id": asset.id,
        "file_name": asset.file_name,
        "current_path": asset.current_path or asset.original_path,
        "file_size": asset.file_size,
        "mtime": asset.mtime,
        "hash_md5": asset.hash_md5,
        "hash_phash": asset.hash_phash,
        "thumbnail_url": f"{thumbnail_base.rstrip('/')}/{asset.id}.jpg",
    }


def list_exact_duplicate_groups(
    session: Session,
    thumbnail_base: str = "/thumbnails",
    limit: int = 20,
) -> list[dict]:
    groups = session.query(DuplicateGroup).order_by(DuplicateGroup.id).limit(limit).all()
    result = []
    for group in groups:
        assets = (
            session.query(Asset)
            .join(DuplicateGroupAsset, DuplicateGroupAsset.asset_id == Asset.id)
            .filter(DuplicateGroupAsset.group_id == group.id)
            .order_by(Asset.id)
            .all()
        )
        result.append(
            {
                "id": group.id,
                "hash_md5": group.hash_md5,
                "asset_count": group.asset_count,
                "status": group.status,
                "assets": [_asset_payload(asset, thumbnail_base) for asset in assets],
            }
        )
    return result


def list_similar_groups(
    session: Session,
    thumbnail_base: str = "/thumbnails",
    limit: int = 20,
) -> list[dict]:
    groups = session.query(SimilarGroup).order_by(SimilarGroup.id).limit(limit).all()
    result = []
    for group in groups:
        assets = (
            session.query(Asset)
            .join(SimilarGroupAsset, SimilarGroupAsset.asset_id == Asset.id)
            .filter(SimilarGroupAsset.group_id == group.id)
            .order_by(Asset.id)
            .all()
        )
        result.append(
            {
                "id": group.id,
                "representative_phash": group.representative_phash,
                "asset_count": group.asset_count,
                "threshold": group.threshold,
                "status": group.status,
                "assets": [_asset_payload(asset, thumbnail_base) for asset in assets],
            }
        )
    return result
