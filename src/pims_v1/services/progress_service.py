from sqlalchemy import case, func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.models.processing import ProcessingTask
from pims_v1.models.review import ReviewItem
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES

PROCESSABLE_ASSET_STATUSES = ("normal", "archived")


def _percent(done: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(done * 100 / total, 2)


def review_progress_summary(session: Session) -> dict[str, object]:
    # Single table scan instead of four separate COUNTs to reduce lock
    # contention with the background workflow on large libraries.
    total_assets, md5_done, phash_done, phash_total = session.query(
        func.count(Asset.id),
        func.count(Asset.hash_md5),
        func.coalesce(
            func.sum(
                case(
                    (
                        Asset.status.in_(PROCESSABLE_ASSET_STATUSES)
                        & Asset.hash_phash.is_not(None),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        Asset.status.in_(PROCESSABLE_ASSET_STATUSES)
                        & Asset.file_ext.in_(sorted(IMAGE_SUFFIXES)),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).one()
    total_assets = int(total_assets or 0)
    md5_done = int(md5_done or 0)
    phash_done = int(phash_done or 0)
    phash_total = int(phash_total or 0)

    task_rows = (
        session.query(
            ProcessingTask.task_type,
            ProcessingTask.status,
            func.count(ProcessingTask.id),
        )
        .group_by(ProcessingTask.task_type, ProcessingTask.status)
        .all()
    )
    tasks = [
        {"task_type": task_type, "status": status, "count": count}
        for task_type, status, count in task_rows
    ]

    operation_rows = (
        session.query(Operation.status, func.count(Operation.id))
        .group_by(Operation.status)
        .all()
    )
    operations = {status: count for status, count in operation_rows}

    batch_rows = (
        session.query(OperationBatch.status, func.count(OperationBatch.id))
        .group_by(OperationBatch.status)
        .all()
    )
    batches = {status: count for status, count in batch_rows}

    return {
        "assets": {
            "total": total_assets,
            "md5_done": md5_done,
            "md5_percent": _percent(md5_done, total_assets),
            "phash_done": phash_done,
            "phash_total": phash_total,
            "phash_percent": _percent(phash_done, phash_total),
        },
        "reviews": {
            "pending": session.query(ReviewItem).filter(ReviewItem.status == "pending").count(),
        },
        "tasks": tasks,
        "operations": operations,
        "batches": batches,
    }
