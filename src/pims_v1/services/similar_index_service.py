from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.review import ReviewItem
from pims_v1.models.similar import SimilarGroup, SimilarGroupAsset


def hamming_distance_hex(left: str, right: str) -> int:
    left_int = int(left, 16)
    right_int = int(right, 16)
    return (left_int ^ right_int).bit_count()


def _clusters(assets: list[Asset], threshold: int) -> list[list[Asset]]:
    clusters: list[list[Asset]] = []
    used_ids: set[int] = set()
    for index, asset in enumerate(assets):
        if asset.id in used_ids:
            continue
        cluster = [asset]
        used_ids.add(asset.id)
        for other in assets[index + 1 :]:
            if other.id in used_ids:
                continue
            if hamming_distance_hex(asset.hash_phash, other.hash_phash) <= threshold:
                cluster.append(other)
                used_ids.add(other.id)
        if len(cluster) > 1:
            clusters.append(cluster)
    return clusters


def build_similar_image_reviews(*, session: Session, threshold: int = 6) -> dict[str, int]:
    assets = (
        session.query(Asset)
        .filter(Asset.hash_phash.is_not(None))
        .order_by(Asset.id)
        .all()
    )
    clusters = _clusters(assets, threshold=threshold)
    review_items_created = 0

    for cluster in clusters:
        representative = cluster[0]
        existing_group = (
            session.query(SimilarGroup)
            .filter(SimilarGroup.representative_phash == representative.hash_phash)
            .one_or_none()
        )
        if existing_group is None:
            group = SimilarGroup(
                representative_phash=representative.hash_phash,
                asset_count=len(cluster),
                threshold=threshold,
            )
            session.add(group)
            session.flush()
        else:
            group = existing_group
            group.asset_count = len(cluster)
            group.threshold = threshold
            session.query(SimilarGroupAsset).filter(SimilarGroupAsset.group_id == group.id).delete()
            session.flush()

        for asset in cluster:
            session.add(SimilarGroupAsset(group_id=group.id, asset_id=asset.id))

        review_item = (
            session.query(ReviewItem)
            .filter(ReviewItem.item_type == "similar_image", ReviewItem.subject_id == group.id)
            .one_or_none()
        )
        if review_item is None:
            session.add(ReviewItem(item_type="similar_image", subject_id=group.id, priority=30))
            review_items_created += 1

    session.commit()
    return {"groups": len(clusters), "review_items": review_items_created}
