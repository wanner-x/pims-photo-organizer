from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.series import Series, SeriesAsset, SeriesCandidate, SeriesCandidateAsset
from pims_v1.services.series_confirm_service import confirm_series_candidate


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
