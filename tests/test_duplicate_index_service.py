from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.review import ReviewItem
from pims_v1.services.duplicate_index_service import build_exact_duplicate_reviews


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_asset(session, library_id: int, path: str, digest: str | None):
    asset_row = Asset(
        library_id=library_id,
        original_path=path,
        current_path=path,
        file_name=path.rsplit("/", 1)[-1],
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
        hash_md5=digest,
    )
    session.add(asset_row)
    session.flush()
    return asset_row


def test_build_exact_duplicate_reviews_creates_group_and_review_item(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    first = add_asset(session, library_row.id, "/library/a.jpg", "abc")
    second = add_asset(session, library_row.id, "/library/b.jpg", "abc")
    add_asset(session, library_row.id, "/library/c.jpg", "def")
    session.commit()

    summary = build_exact_duplicate_reviews(session=session)

    group = session.query(DuplicateGroup).one()
    members = session.query(DuplicateGroupAsset).order_by(DuplicateGroupAsset.asset_id).all()
    review_item = session.query(ReviewItem).one()
    assert summary == {"groups": 1, "review_items": 1}
    assert group.hash_md5 == "abc"
    assert group.asset_count == 2
    assert [member.asset_id for member in members] == [first.id, second.id]
    assert review_item.item_type == "duplicate_exact"
    assert review_item.subject_id == group.id


def test_build_exact_duplicate_reviews_is_idempotent(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    add_asset(session, library_row.id, "/library/a.jpg", "abc")
    add_asset(session, library_row.id, "/library/b.jpg", "abc")
    session.commit()

    first_summary = build_exact_duplicate_reviews(session=session)
    second_summary = build_exact_duplicate_reviews(session=session)

    assert first_summary == {"groups": 1, "review_items": 1}
    assert second_summary == {"groups": 1, "review_items": 0}
    assert session.query(DuplicateGroup).count() == 1
    assert session.query(DuplicateGroupAsset).count() == 2
    assert session.query(ReviewItem).count() == 1
