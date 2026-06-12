from pathlib import PurePosixPath
from pathlib import Path
import re
import shutil

from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.series import Series, SeriesAsset, SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion


def safe_series_path_segment(title: str) -> str:
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

    title = safe_series_path_segment(candidate.title or PurePosixPath(candidate.source_root).name)
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


def _unique_archive_dir(session: Session, archive_root: str, category: str, title: str) -> Path:
    root = Path(archive_root)
    category_root = root / safe_series_path_segment(category)
    base = category_root / safe_series_path_segment(title)
    candidate = base
    counter = 1
    while session.query(Series.id).filter(Series.archive_path == str(candidate)).first() is not None:
        candidate = category_root / f"{base.name}-{counter}"
        counter += 1
    return candidate


def _unique_file_path(destination_dir: Path, file_name: str) -> Path:
    destination = destination_dir / file_name
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while True:
        candidate = destination_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def confirm_series_suggestion(
    *,
    session: Session,
    suggestion_id: int,
    archive_root: str,
    title: str | None = None,
    category: str | None = None,
) -> dict[str, int | str]:
    suggestion = session.get(SeriesSuggestion, suggestion_id)
    if suggestion is None:
        raise ValueError(f"Series suggestion not found: {suggestion_id}")
    if suggestion.status != "pending_review":
        raise ValueError(f"Series suggestion is not pending review: {suggestion.status}")

    candidate = session.get(SeriesCandidate, suggestion.candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {suggestion.candidate_id}")

    final_title = safe_series_path_segment(title or suggestion.suggested_title)
    final_category = safe_series_path_segment(category or suggestion.suggested_category or "未分类")
    archive_dir = _unique_archive_dir(session, archive_root, final_category, final_title)
    archive_dir.mkdir(parents=True, exist_ok=True)
    series = Series(
        library_id=candidate.library_id,
        title=final_title,
        archive_path=str(archive_dir),
        status="confirmed",
    )
    session.add(series)
    session.flush()

    rows = (
        session.query(SeriesCandidateAsset)
        .filter(SeriesCandidateAsset.candidate_id == candidate.id)
        .order_by(SeriesCandidateAsset.sort_order, SeriesCandidateAsset.id)
        .all()
    )
    moved = 0
    failed = 0
    for row in rows:
        asset = session.get(Asset, row.asset_id)
        if asset is None:
            failed += 1
            continue
        source = Path(asset.current_path or asset.original_path)
        destination = _unique_file_path(archive_dir, asset.file_name or source.name)
        try:
            if source.resolve() != destination.resolve():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
            asset.current_path = str(destination)
            asset.status = "archived"
            session.add(
                SeriesAsset(
                    series_id=series.id,
                    asset_id=asset.id,
                    sort_order=row.sort_order,
                )
            )
            moved += 1
        except Exception:
            failed += 1

    candidate.title = final_title
    candidate.status = "confirmed" if failed == 0 else "failed"
    candidate.confidence = max(candidate.confidence, suggestion.confidence, 0.9 if failed == 0 else 0.0)
    suggestion.suggested_title = final_title
    suggestion.suggested_category = final_category
    suggestion.status = "confirmed" if failed == 0 else "failed"
    series.status = "confirmed" if failed == 0 else "failed"
    session.commit()
    return {
        "candidate_id": candidate.id,
        "suggestion_id": suggestion.id,
        "series_id": series.id,
        "archive_path": series.archive_path,
        "moved": moved,
        "failed": failed,
        "status": suggestion.status,
    }
