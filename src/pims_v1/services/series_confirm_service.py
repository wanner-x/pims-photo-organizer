from pathlib import PurePosixPath
import re

from sqlalchemy.orm import Session

from pims_v1.models.series import Series, SeriesAsset, SeriesCandidate, SeriesCandidateAsset


def _safe_title(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Untitled Series"


def _unique_archive_path(session: Session, archive_root: str, title: str) -> str:
    root = PurePosixPath(archive_root.replace("\\", "/"))
    base = str(root / title)
    candidate = base
    counter = 1
    while session.query(Series.id).filter(Series.archive_path == candidate).first() is not None:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def confirm_series_candidate(
    *,
    session: Session,
    candidate_id: int,
    archive_root: str,
) -> dict[str, int | str]:
    candidate = session.get(SeriesCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {candidate_id}")

    title = _safe_title(candidate.title or PurePosixPath(candidate.source_root).name)
    archive_path = _unique_archive_path(session, archive_root, title)
    series = Series(
        library_id=candidate.library_id,
        title=title,
        archive_path=archive_path,
        status="confirmed",
    )
    session.add(series)
    session.flush()

    rows = (
        session.query(SeriesCandidateAsset)
        .filter(SeriesCandidateAsset.candidate_id == candidate_id)
        .order_by(SeriesCandidateAsset.sort_order, SeriesCandidateAsset.id)
        .all()
    )
    for row in rows:
        session.add(
            SeriesAsset(
                series_id=series.id,
                asset_id=row.asset_id,
                sort_order=row.sort_order,
            )
        )

    candidate.title = title
    candidate.status = "confirmed"
    candidate.confidence = max(candidate.confidence, 0.9)
    session.commit()
    return {
        "candidate_id": candidate.id,
        "series_id": series.id,
        "archive_path": series.archive_path,
    }
