from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup
from pims_v1.models.library import Library
from pims_v1.models.review import ReviewItem
from pims_v1.models.series import SeriesCandidate


def database_status(session: Session) -> dict[str, int]:
    return {
        "libraries": session.query(Library).count(),
        "assets": session.query(Asset).count(),
        "assets_with_md5": session.query(Asset).filter(Asset.hash_md5.is_not(None)).count(),
        "assets_with_phash": session.query(Asset).filter(Asset.hash_phash.is_not(None)).count(),
        "duplicate_groups": session.query(DuplicateGroup).count(),
        "series_candidates": session.query(SeriesCandidate).count(),
        "review_items_pending": session.query(ReviewItem).filter(ReviewItem.status == "pending").count(),
    }
