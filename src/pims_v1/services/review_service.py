from sqlalchemy import func
from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.similar import SimilarGroup, SimilarGroupAsset
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset


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
