from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.services.hash_index_service import compute_missing_md5


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_library(session, root_path: str) -> Library:
    library_row = Library(name="Library", kind="local", root_path=root_path)
    session.add(library_row)
    session.commit()
    return library_row


def test_compute_missing_md5_updates_assets(tmp_path):
    sample = tmp_path / "a.jpg"
    sample.write_bytes(b"same-content")
    session = make_session(tmp_path)
    library_row = add_library(session, str(tmp_path))
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(sample),
        current_path=str(sample),
        file_name=sample.name,
        file_ext=".jpg",
        file_size=sample.stat().st_size,
        mtime=sample.stat().st_mtime,
    )
    session.add(asset_row)
    session.commit()

    summary = compute_missing_md5(session=session, limit=10)

    stored = session.query(Asset).one()
    assert summary == {"processed": 1, "skipped_missing": 0, "skipped_oversize": 0}
    assert stored.hash_md5 == "f8aeb3a8368e8d146968c49124a2dd98"
    assert stored.stage == "md5_done"


def test_compute_missing_md5_skips_oversize_assets(tmp_path):
    sample = tmp_path / "large.jpg"
    sample.write_bytes(b"large-content")
    session = make_session(tmp_path)
    library_row = add_library(session, str(tmp_path))
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(sample),
        current_path=str(sample),
        file_name=sample.name,
        file_ext=".jpg",
        file_size=sample.stat().st_size,
        mtime=sample.stat().st_mtime,
    )
    session.add(asset_row)
    session.commit()

    summary = compute_missing_md5(session=session, limit=10, max_bytes=1)

    stored = session.query(Asset).one()
    assert summary == {"processed": 0, "skipped_missing": 0, "skipped_oversize": 1}
    assert stored.hash_md5 is None
