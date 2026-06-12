from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.models.processing import ProcessingTask
from pims_v1.models.review import ReviewItem
from pims_v1.services.phash_index_service import IMAGE_SUFFIXES


def _percent(done: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(done * 100 / total, 2)


def review_progress_summary(session: Session) -> dict[str, object]:
    total_assets = session.query(Asset).count()
    md5_done = session.query(Asset).filter(Asset.hash_md5.is_not(None)).count()
    phash_total = session.query(Asset).filter(Asset.file_ext.in_(sorted(IMAGE_SUFFIXES))).count()
    phash_done = session.query(Asset).filter(Asset.hash_phash.is_not(None)).count()

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
