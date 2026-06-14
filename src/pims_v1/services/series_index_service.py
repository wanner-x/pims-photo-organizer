from collections import defaultdict
from pathlib import PurePath

from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.review import ReviewItem
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset


def build_series_candidates(*, session: Session, min_assets: int = 2, limit: int | None = None) -> dict[str, int]:
    grouped: dict[tuple[int, str], list[Asset]] = defaultdict(list)
    query = session.query(Asset).order_by(Asset.library_id, Asset.original_path)
    if limit is not None:
        query = query.limit(limit)
    assets = query.all()
    for asset in assets:
        source_root = PurePath(asset.original_path).parent.as_posix()
        grouped[(asset.library_id, source_root)].append(asset)

    candidates_seen = 0
    review_items_created = 0
    for (library_id, source_root), grouped_assets in sorted(grouped.items()):
        if len(grouped_assets) < min_assets:
            continue
        candidates_seen += 1
        candidate = (
            session.query(SeriesCandidate)
            .filter(
                SeriesCandidate.library_id == library_id,
                SeriesCandidate.source_root == source_root,
            )
            .one_or_none()
        )
        if candidate is None:
            candidate = SeriesCandidate(
                library_id=library_id,
                source_root=source_root,
                title=PurePath(source_root).name,
                confidence=0.75,
            )
            session.add(candidate)
            session.flush()
        else:
            candidate.title = candidate.title or PurePath(source_root).name
            session.query(SeriesCandidateAsset).filter(
                SeriesCandidateAsset.candidate_id == candidate.id
            ).delete()
            session.flush()

        for sort_order, asset in enumerate(grouped_assets):
            session.add(
                SeriesCandidateAsset(
                    candidate_id=candidate.id,
                    asset_id=asset.id,
                    sort_order=sort_order,
                )
            )

        review_item = (
            session.query(ReviewItem)
            .filter(
                ReviewItem.item_type == "series_confirm",
                ReviewItem.subject_id == candidate.id,
            )
            .one_or_none()
        )
        if review_item is None:
            session.add(ReviewItem(item_type="series_confirm", subject_id=candidate.id, priority=50))
            review_items_created += 1

    session.commit()
    return {"candidates": candidates_seen, "review_items": review_items_created}
