from pathlib import Path

from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.processing import ProcessingTask
from pims_v1.services.duplicate_index_service import build_exact_duplicate_reviews
from pims_v1.services.operation_plan_service import create_duplicate_quarantine_plan
from pims_v1.services.series_index_service import build_series_candidates
from pims_v1.services.similar_index_service import build_similar_image_reviews
from pims_v1.services.task_service import enqueue_task, recover_stale_tasks
from pims_v1.services.task_worker_service import process_md5_tasks, process_phash_tasks
from pims_v1.services.thumbnail_service import ensure_thumbnail


def _enqueue_hash_tasks(session: Session, task_type: str, hash_column, limit: int) -> int:
    query = session.query(Asset).filter(hash_column.is_(None)).order_by(Asset.id).limit(limit)
    queued = 0
    for asset in query.all():
        existing = (
            session.query(ProcessingTask.id)
            .filter(
                ProcessingTask.task_type == task_type,
                ProcessingTask.subject_type == "asset",
                ProcessingTask.subject_id == asset.id,
                ProcessingTask.status.in_(("pending", "running")),
            )
            .first()
        )
        enqueue_task(session, task_type, "asset", asset.id)
        if existing is None:
            queued += 1
    return queued


def _build_thumbnails(session: Session, cache_root: str | Path, limit: int) -> dict[str, int]:
    summary = {
        "created": 0,
        "exists": 0,
        "skipped_non_image": 0,
        "missing": 0,
        "failed": 0,
    }
    assets = session.query(Asset).order_by(Asset.id).limit(limit).all()
    for asset in assets:
        result = ensure_thumbnail(session=session, asset_id=asset.id, cache_root=cache_root)
        status = str(result["status"])
        if status in summary:
            summary[status] += 1
    return summary


def run_safe_workflow(
    *,
    session: Session,
    keep_root: str | None,
    cache_root: str | Path,
    md5_limit: int = 1000,
    phash_limit: int = 1000,
    thumbnail_limit: int = 1000,
    min_series_assets: int = 2,
    similar_threshold: int = 6,
    stale_after_seconds: int = 300,
) -> dict[str, dict[str, int]]:
    recovered = recover_stale_tasks(session, stale_after_seconds=stale_after_seconds)
    md5_queued = _enqueue_hash_tasks(session, "hash_md5", Asset.hash_md5, md5_limit)
    md5 = process_md5_tasks(session=session, limit=md5_limit)
    duplicates = build_exact_duplicate_reviews(session=session)
    phash_queued = _enqueue_hash_tasks(session, "hash_phash", Asset.hash_phash, phash_limit)
    phash = process_phash_tasks(session=session, limit=phash_limit)
    similar = build_similar_image_reviews(session=session, threshold=similar_threshold)
    series = build_series_candidates(session=session, min_assets=min_series_assets)
    thumbnails = _build_thumbnails(session=session, cache_root=cache_root, limit=thumbnail_limit)

    duplicate_plan = {"batch_id": 0, "operations": 0}
    if keep_root:
        duplicate_plan = create_duplicate_quarantine_plan(session=session, keep_root=keep_root)

    return {
        "recovered": recovered,
        "md5_enqueued": {"queued": md5_queued},
        "md5": md5,
        "duplicates": duplicates,
        "phash_enqueued": {"queued": phash_queued},
        "phash": phash,
        "similar": similar,
        "series": series,
        "thumbnails": thumbnails,
        "duplicate_plan": duplicate_plan,
    }
