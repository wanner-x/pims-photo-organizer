from sqlalchemy import func
from sqlalchemy.orm import Session

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
