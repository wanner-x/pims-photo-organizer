from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.series import Series, SeriesAsset, SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.services.series_confirm_service import confirm_series_candidate, confirm_series_suggestion


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_candidate(session):
    library_row = Library(name="Photos", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    second = Asset(
        library_id=library_row.id,
        original_path="/library/set/b.jpg",
        current_path="/library/set/b.jpg",
        file_name="b.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add_all([first, second])
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/set",
        title="Model: Set 01?",
        status="ai_suggested",
    )
    session.add(candidate)
    session.flush()
    session.add_all(
        [
            SeriesCandidateAsset(candidate_id=candidate.id, asset_id=first.id, sort_order=0),
            SeriesCandidateAsset(candidate_id=candidate.id, asset_id=second.id, sort_order=1),
        ]
    )
    session.commit()
    return candidate


def test_confirm_series_candidate_creates_series_and_assets(tmp_path):
    session = make_session(tmp_path)
    candidate = add_candidate(session)

    result = confirm_series_candidate(
        session=session,
        candidate_id=candidate.id,
        archive_root="/nas/archive",
    )

    series_row = session.query(Series).one()
    series_assets = session.query(SeriesAsset).order_by(SeriesAsset.sort_order).all()
    session.refresh(candidate)
    assert result == {
        "candidate_id": candidate.id,
        "series_id": series_row.id,
        "archive_path": "/nas/archive/Model Set 01",
    }
    assert series_row.title == "Model Set 01"
    assert series_row.archive_path == "/nas/archive/Model Set 01"
    assert [row.sort_order for row in series_assets] == [0, 1]
    assert candidate.status == "confirmed"


def test_confirm_series_candidate_makes_archive_path_unique(tmp_path):
    session = make_session(tmp_path)
    candidate = add_candidate(session)
    session.add(
        Series(
            library_id=candidate.library_id,
            title="Model Set 01",
            archive_path="/nas/archive/Model Set 01",
        )
    )
    session.commit()

    result = confirm_series_candidate(
        session=session,
        candidate_id=candidate.id,
        archive_root="/nas/archive",
    )

    assert result["archive_path"] == "/nas/archive/Model Set 01-1"


def test_confirm_series_suggestion_moves_assets_to_archive_and_updates_paths(tmp_path):
    session = make_session(tmp_path)
    source_root = tmp_path / "pc" / "set"
    source_root.mkdir(parents=True)
    first_file = source_root / "a.jpg"
    second_file = source_root / "b.jpg"
    first_file.write_bytes(b"first")
    second_file.write_bytes(b"second")
    archive_root = tmp_path / "nas"
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    first = Asset(
        library_id=library_row.id,
        original_path=str(first_file),
        current_path=str(first_file),
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=first_file.stat().st_size,
        mtime=1.0,
    )
    second = Asset(
        library_id=library_row.id,
        original_path=str(second_file),
        current_path=str(second_file),
        file_name="b.jpg",
        file_ext=".jpg",
        file_size=second_file.stat().st_size,
        mtime=1.0,
    )
    session.add_all([first, second])
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root=str(source_root),
        title="旧标题",
        status="ai_suggested",
    )
    session.add(candidate)
    session.flush()
    session.add_all(
        [
            SeriesCandidateAsset(candidate_id=candidate.id, asset_id=first.id, sort_order=0),
            SeriesCandidateAsset(candidate_id=candidate.id, asset_id=second.id, sort_order=1),
        ]
    )
    session.flush()
    suggestion = SeriesSuggestion(
        candidate_id=candidate.id,
        suggested_title="海边 清晨?",
        suggested_category="写真/合集",
        confidence=0.82,
        status="pending_review",
    )
    session.add(suggestion)
    session.commit()

    result = confirm_series_suggestion(
        session=session,
        suggestion_id=suggestion.id,
        archive_root=str(archive_root),
    )

    destination_dir = archive_root / "写真 合集" / "海边 清晨"
    assert result["moved"] == 2
    assert result["failed"] == 0
    assert result["archive_path"] == str(destination_dir)
    assert not first_file.exists()
    assert not second_file.exists()
    assert (destination_dir / "a.jpg").read_bytes() == b"first"
    assert (destination_dir / "b.jpg").read_bytes() == b"second"
    session.refresh(first)
    session.refresh(second)
    session.refresh(candidate)
    session.refresh(suggestion)
    assert first.current_path == str(destination_dir / "a.jpg")
    assert second.current_path == str(destination_dir / "b.jpg")
    assert first.status == "archived"
    assert candidate.status == "confirmed"
    assert suggestion.status == "confirmed"
    assert session.query(Series).one().title == "海边 清晨"
    assert session.query(SeriesAsset).count() == 2
