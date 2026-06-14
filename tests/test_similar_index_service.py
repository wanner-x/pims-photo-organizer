from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series, similar
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.review import ReviewItem
from pims_v1.models.similar import SimilarGroup, SimilarGroupAsset
from pims_v1.services.similar_index_service import build_similar_image_reviews, hamming_distance_hex


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_asset(session, library_id: int, path: str, phash: str):
    asset_row = Asset(
        library_id=library_id,
        original_path=path,
        current_path=path,
        file_name=path.rsplit("/", 1)[-1],
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
        hash_phash=phash,
    )
    session.add(asset_row)
    session.flush()
    return asset_row


def test_hamming_distance_hex_counts_bit_differences():
    assert hamming_distance_hex("0000", "0001") == 1
    assert hamming_distance_hex("0000", "ffff") == 16


def test_build_similar_image_reviews_creates_group_for_close_phashes(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = add_asset(session, library_row.id, "/library/a.jpg", "0000")
    second = add_asset(session, library_row.id, "/library/b.jpg", "0001")
    add_asset(session, library_row.id, "/library/c.jpg", "ffff")
    session.commit()

    summary = build_similar_image_reviews(session=session, threshold=1)

    group = session.query(SimilarGroup).one()
    members = session.query(SimilarGroupAsset).order_by(SimilarGroupAsset.asset_id).all()
    review_item = session.query(ReviewItem).one()
    assert summary == {"groups": 1, "review_items": 1}
    assert group.asset_count == 2
    assert [member.asset_id for member in members] == [first.id, second.id]
    assert review_item.item_type == "similar_image"
    assert review_item.subject_id == group.id


def test_build_similar_image_reviews_respects_limit(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = add_asset(session, library_row.id, "/library/a.jpg", "0000")
    second = add_asset(session, library_row.id, "/library/b.jpg", "0001")
    add_asset(session, library_row.id, "/library/c.jpg", "00f0")
    add_asset(session, library_row.id, "/library/d.jpg", "00f1")
    session.commit()

    summary = build_similar_image_reviews(session=session, threshold=1, limit=2)

    members = session.query(SimilarGroupAsset).order_by(SimilarGroupAsset.asset_id).all()
    assert summary == {"groups": 1, "review_items": 1}
    assert [member.asset_id for member in members] == [first.id, second.id]
