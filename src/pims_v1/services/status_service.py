from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup
from pims_v1.models.library import Library
from pims_v1.models.processing import ProcessingTask
from pims_v1.models.review import ReviewItem
from pims_v1.models.series import SeriesCandidate


def database_status(session: Session) -> dict[str, int]:
    asset_total, asset_md5, asset_phash = session.query(
        func.count(Asset.id),
        func.count(Asset.hash_md5),
        func.count(Asset.hash_phash),
    ).one()

    task_counts = {
        status: count
        for status, count in session.query(ProcessingTask.status, func.count(ProcessingTask.id))
        .group_by(ProcessingTask.status)
        .all()
    }

    return {
        "libraries": session.query(Library).count(),
        "assets": int(asset_total or 0),
        "assets_with_md5": int(asset_md5 or 0),
        "assets_with_phash": int(asset_phash or 0),
        "duplicate_groups": session.query(DuplicateGroup).count(),
        "series_candidates": session.query(SeriesCandidate).count(),
        "review_items_pending": session.query(ReviewItem).filter(ReviewItem.status == "pending").count(),
        "tasks_pending": task_counts.get("pending", 0),
        "tasks_running": task_counts.get("running", 0),
        "tasks_failed": task_counts.get("failed", 0),
        "tasks_completed": task_counts.get("completed", 0),
    }
