from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.review import ReviewItem


def build_exact_duplicate_reviews(*, session: Session) -> dict[str, int]:
    duplicate_rows = (
        session.query(Asset.hash_md5, func.count(Asset.id))
        .filter(Asset.hash_md5.is_not(None))
        .group_by(Asset.hash_md5)
        .having(func.count(Asset.id) > 1)
        .all()
    )
    review_items_created = 0

    for digest, asset_count in duplicate_rows:
        group = session.query(DuplicateGroup).filter(DuplicateGroup.hash_md5 == digest).one_or_none()
        if group is None:
            group = DuplicateGroup(hash_md5=digest, asset_count=asset_count)
            session.add(group)
            session.flush()
        else:
            group.asset_count = asset_count
            session.query(DuplicateGroupAsset).filter(
                DuplicateGroupAsset.group_id == group.id
            ).delete()
            session.flush()

        assets = session.query(Asset).filter(Asset.hash_md5 == digest).order_by(Asset.id).all()
        for asset in assets:
            session.add(DuplicateGroupAsset(group_id=group.id, asset_id=asset.id))

        review_item = (
            session.query(ReviewItem)
            .filter(
                ReviewItem.item_type == "duplicate_exact",
                ReviewItem.subject_id == group.id,
            )
            .one_or_none()
        )
        if review_item is None:
            session.add(
                ReviewItem(
                    item_type="duplicate_exact",
                    subject_id=group.id,
                    priority=10,
                )
            )
            review_items_created += 1

    session.commit()
    return {"groups": len(duplicate_rows), "review_items": review_items_created}
