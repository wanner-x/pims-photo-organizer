from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.services.phash_index_service import compute_missing_phash


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


def test_compute_missing_phash_updates_image_assets(tmp_path):
    sample = tmp_path / "a.jpg"
    Image.new("RGB", (32, 32), color="white").save(sample)
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

    summary = compute_missing_phash(session=session, limit=10)

    stored = session.query(Asset).one()
    assert summary == {"processed": 1, "skipped_missing": 0, "skipped_non_image": 0, "failed": 0}
    assert stored.hash_phash is not None
    assert stored.stage == "phash_done"


def test_compute_missing_phash_skips_non_image_assets(tmp_path):
    sample = tmp_path / "a.mp4"
    sample.write_bytes(b"video")
    session = make_session(tmp_path)
    library_row = add_library(session, str(tmp_path))
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(sample),
        current_path=str(sample),
        file_name=sample.name,
        file_ext=".mp4",
        file_size=sample.stat().st_size,
        mtime=sample.stat().st_mtime,
    )
    session.add(asset_row)
    session.commit()

    summary = compute_missing_phash(session=session, limit=10)

    stored = session.query(Asset).one()
    assert summary == {"processed": 0, "skipped_missing": 0, "skipped_non_image": 1, "failed": 0}
    assert stored.hash_phash is None


def test_compute_missing_phash_counts_decompression_bomb_as_failed(tmp_path, monkeypatch):
    import pims_v1.services.image_open_service as image_open_service

    sample = tmp_path / "huge.jpg"
    Image.new("RGB", (32, 32), color="white").save(sample)
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

    def raise_decompression_bomb(_path):
        raise Image.DecompressionBombWarning("too many pixels")

    monkeypatch.setattr(image_open_service.Image, "open", raise_decompression_bomb)

    summary = compute_missing_phash(session=session, limit=10)

    stored = session.query(Asset).one()
    assert summary == {"processed": 0, "skipped_missing": 0, "skipped_non_image": 0, "failed": 1}
    assert stored.hash_phash is None
