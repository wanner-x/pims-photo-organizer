from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from pims_v1.config import settings
from pims_v1.models.asset import Asset
from pims_v1.models.processing import ProcessingTask
from pims_v1.services.ai_naming_service import NamingClient
from pims_v1.services.archive_decision_service import auto_archive_candidates
from pims_v1.services.duplicate_index_service import build_exact_duplicate_reviews
from pims_v1.services.notification_service import notify_duplicate_approval_needed
from pims_v1.services.operation_plan_service import create_duplicate_quarantine_plan
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES
from pims_v1.services.series_index_service import build_series_candidates
from pims_v1.services.similar_index_service import build_similar_image_reviews
from pims_v1.services.task_service import recover_stale_tasks
from pims_v1.services.task_worker_service import process_md5_tasks, process_phash_tasks
from pims_v1.services.thumbnail_service import ensure_thumbnail


ProgressCallback = Callable[[dict[str, int | str]], None]


def _empty_archive_auto_summary() -> dict[str, int]:
    return {
        "considered": 0,
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


def _active_task_subject_ids(session: Session, task_type: str, asset_ids: list[int]) -> set[int]:
    if not asset_ids:
        return set()
    rows = (
        session.query(ProcessingTask.subject_id)
        .filter(
            ProcessingTask.task_type == task_type,
            ProcessingTask.subject_type == "asset",
            ProcessingTask.subject_id.in_(asset_ids),
            ProcessingTask.status.in_(("pending", "running")),
        )
        .all()
    )
    return {row.subject_id for row in rows}


def _enqueue_hash_tasks(session: Session, task_type: str, hash_column, limit: int) -> int:
    query = session.query(Asset).filter(hash_column.is_(None)).order_by(Asset.id).limit(limit)
    assets = query.all()
    existing_subject_ids = _active_task_subject_ids(session, task_type, [asset.id for asset in assets])
    tasks = [
        ProcessingTask(
            task_type=task_type,
            subject_type="asset",
            subject_id=asset.id,
        )
        for asset in assets
        if asset.id not in existing_subject_ids
    ]
    session.add_all(tasks)
    session.commit()
    return len(tasks)


def _enqueue_phash_tasks(session: Session, limit: int) -> int:
    query = (
        session.query(Asset)
        .filter(Asset.hash_phash.is_(None))
        .filter(Asset.file_ext.in_(sorted(IMAGE_SUFFIXES)))
        .order_by(Asset.id)
        .limit(limit)
    )
    assets = query.all()
    existing_subject_ids = _active_task_subject_ids(session, "hash_phash", [asset.id for asset in assets])
    tasks = [
        ProcessingTask(
            task_type="hash_phash",
            subject_type="asset",
            subject_id=asset.id,
        )
        for asset in assets
        if asset.id not in existing_subject_ids
    ]
    session.add_all(tasks)
    session.commit()
    return len(tasks)


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


def _notify_duplicate_plan_if_needed(session: Session, duplicate_plan: dict[str, int]) -> dict[str, int]:
    if duplicate_plan.get("operations", 0) <= 0 or not settings.wechat_webhook_url:
        return {"sent": 0, "failed": 0, "skipped": 0}

    batch_id = duplicate_plan["batch_id"]
    operations = duplicate_plan["operations"]
    return notify_duplicate_approval_needed(
        session=session,
        webhook_url=settings.wechat_webhook_url,
        batch_id=batch_id,
        operations=operations,
        review_url=settings.review_url,
    )


def run_safe_workflow(
    *,
    session: Session,
    keep_root: str | None,
    cache_root: str | Path,
    md5_limit: int = 1000,
    phash_limit: int = 1000,
    thumbnail_limit: int = 1000,
    min_series_assets: int = 2,
    auto_archive_limit: int = 20,
    similar_threshold: int = 6,
    stale_after_seconds: int = 300,
    archive_client: NamingClient | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, dict[str, int]]:
    recovered = recover_stale_tasks(session, stale_after_seconds=stale_after_seconds)
    md5_queued = _enqueue_hash_tasks(session, "hash_md5", Asset.hash_md5, md5_limit)
    md5 = process_md5_tasks(
        session=session,
        limit=md5_limit,
        progress_callback=progress_callback,
    )
    duplicates = build_exact_duplicate_reviews(session=session)
    phash_queued = _enqueue_phash_tasks(session, phash_limit)
    phash = process_phash_tasks(
        session=session,
        limit=phash_limit,
        progress_callback=progress_callback,
    )
    similar = build_similar_image_reviews(session=session, threshold=similar_threshold)
    series = build_series_candidates(session=session, min_assets=min_series_assets)
    thumbnails = _build_thumbnails(session=session, cache_root=cache_root, limit=thumbnail_limit)
    archive_auto = _empty_archive_auto_summary()
    if keep_root and auto_archive_limit > 0 and archive_client is not None:
        archive_auto = auto_archive_candidates(
            session=session,
            archive_root=keep_root,
            client=archive_client,
            limit=auto_archive_limit,
        )

    duplicate_plan = {"batch_id": 0, "operations": 0}
    if keep_root:
        duplicate_plan = create_duplicate_quarantine_plan(session=session, keep_root=keep_root)
    notification = _notify_duplicate_plan_if_needed(session, duplicate_plan)

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
        "archive_auto": archive_auto,
        "duplicate_plan": duplicate_plan,
        "notification": notification,
    }
