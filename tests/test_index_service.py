from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.services.index_service import index_library


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_index_library_persists_media_assets_without_touching_files(tmp_path):
    root = tmp_path / "library"
    nested = root / "set1"
    nested.mkdir(parents=True)
    first = nested / "a.jpg"
    second = nested / "b.mp4"
    ignored = nested / "notes.txt"
    first.write_bytes(b"jpg")
    second.write_bytes(b"mp4")
    ignored.write_bytes(b"text")
    session = make_session(tmp_path)

    summary = index_library(
        session=session,
        name="NAS photos",
        kind="nas",
        root_path=root,
        limit=None,
    )

    stored_library = session.query(Library).one()
    stored_assets = session.query(Asset).order_by(Asset.file_name).all()

    assert summary == {"discovered": 2, "created": 2, "updated": 0}
    assert stored_library.name == "NAS photos"
    assert stored_library.kind == "nas"
    assert stored_library.root_path == str(root)
    assert [item.file_name for item in stored_assets] == ["a.jpg", "b.mp4"]
    assert {item.file_ext for item in stored_assets} == {".jpg", ".mp4"}
    assert first.exists()
    assert second.exists()
    assert ignored.exists()


def test_index_library_updates_existing_asset_instead_of_duplicating(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    sample = root / "a.jpg"
    sample.write_bytes(b"jpg")
    session = make_session(tmp_path)

    first_summary = index_library(
        session=session,
        name="Local photos",
        kind="local",
        root_path=root,
        limit=None,
    )
    sample.write_bytes(b"larger-jpg")
    second_summary = index_library(
        session=session,
        name="Local photos",
        kind="local",
        root_path=root,
        limit=None,
    )

    assets = session.query(Asset).all()

    assert first_summary == {"discovered": 1, "created": 1, "updated": 0}
    assert second_summary == {"discovered": 1, "created": 0, "updated": 1}
    assert len(assets) == 1
    assert assets[0].file_size == len(b"larger-jpg")
