from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.review import ReviewItem
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset
from pims_v1.services.series_index_service import build_series_candidates


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_asset(session, library_id: int, path: str):
    asset_row = Asset(
        library_id=library_id,
        original_path=path,
        current_path=path,
        file_name=path.rsplit("/", 1)[-1],
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    return asset_row


def test_build_series_candidates_groups_assets_by_parent_folder(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = add_asset(session, library_row.id, "/library/set1/a.jpg")
    second = add_asset(session, library_row.id, "/library/set1/b.jpg")
    add_asset(session, library_row.id, "/library/set2/c.jpg")
    session.commit()

    summary = build_series_candidates(session=session, min_assets=2)

    candidate = session.query(SeriesCandidate).one()
    members = session.query(SeriesCandidateAsset).order_by(SeriesCandidateAsset.asset_id).all()
    review_item = session.query(ReviewItem).one()
    assert summary == {"candidates": 1, "review_items": 1}
    assert candidate.source_root == "/library/set1"
    assert candidate.title == "set1"
    assert [member.asset_id for member in members] == [first.id, second.id]
    assert review_item.item_type == "series_confirm"
    assert review_item.subject_id == candidate.id


def test_build_series_candidates_is_idempotent(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    add_asset(session, library_row.id, "/library/set1/a.jpg")
    add_asset(session, library_row.id, "/library/set1/b.jpg")
    session.commit()

    first_summary = build_series_candidates(session=session, min_assets=2)
    second_summary = build_series_candidates(session=session, min_assets=2)

    assert first_summary == {"candidates": 1, "review_items": 1}
    assert second_summary == {"candidates": 1, "review_items": 0}
    assert session.query(SeriesCandidate).count() == 1
    assert session.query(SeriesCandidateAsset).count() == 2
    assert session.query(ReviewItem).count() == 1
