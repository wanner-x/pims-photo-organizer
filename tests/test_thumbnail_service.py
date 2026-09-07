from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.services.safe_workflow_service import build_pending_thumbnails
from pims_v1.services.thumbnail_service import ensure_thumbnail


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def add_asset(session, path):
    library_row = Library(name="Photos", kind="local", root_path=str(path.parent))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(path),
        current_path=str(path),
        file_name=path.name,
        file_ext=path.suffix,
        file_size=path.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    return asset_row


def test_ensure_thumbnail_creates_cached_jpeg(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    source = tmp_path / "a.jpg"
    Image.new("RGB", (100, 80), color="white").save(source)
    asset_row = add_asset(session, source)

    result = ensure_thumbnail(
        session=session,
        asset_id=asset_row.id,
        cache_root=tmp_path / ".cache",
        size=(32, 32),
    )

    thumbnail_path = tmp_path / ".cache" / "thumbnails" / f"{asset_row.id}.jpg"
    assert result == {
        "asset_id": asset_row.id,
        "status": "created",
        "path": str(thumbnail_path),
    }
    assert thumbnail_path.exists()
    with Image.open(thumbnail_path) as image:
        assert image.size[0] <= 32
        assert image.size[1] <= 32


def test_ensure_thumbnail_reuses_existing_cached_file(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    source = tmp_path / "a.jpg"
    Image.new("RGB", (100, 80), color="white").save(source)
    asset_row = add_asset(session, source)

    first = ensure_thumbnail(session=session, asset_id=asset_row.id, cache_root=tmp_path / ".cache")
    second = ensure_thumbnail(session=session, asset_id=asset_row.id, cache_root=tmp_path / ".cache")

    assert first["status"] == "created"
    assert second["status"] == "exists"
    assert first["path"] == second["path"]


def test_ensure_thumbnail_reports_non_image(tmp_path):
    session = make_session(tmp_path)
    source = tmp_path / "a.txt"
    source.write_text("not an image", encoding="utf-8")
    asset_row = add_asset(session, source)

    result = ensure_thumbnail(session=session, asset_id=asset_row.id, cache_root=tmp_path / ".cache")

    assert result == {
        "asset_id": asset_row.id,
        "status": "skipped_non_image",
        "path": None,
    }


def test_build_pending_thumbnails_advances_past_existing(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    asset_ids = []
    for index in range(3):
        source = tmp_path / f"img_{index}.jpg"
        Image.new("RGB", (40, 40), color="white").save(source)
        asset_row = Asset(
            library_id=library_row.id,
            original_path=str(source),
            current_path=str(source),
            file_name=source.name,
            file_ext=".jpg",
            file_size=source.stat().st_size,
            mtime=1.0,
        )
        session.add(asset_row)
        session.flush()
        asset_ids.append(asset_row.id)
    session.commit()
    cache_root = tmp_path / ".cache"

    first = build_pending_thumbnails(session=session, cache_root=cache_root, limit=1)
    second = build_pending_thumbnails(session=session, cache_root=cache_root, limit=1)
    third = build_pending_thumbnails(session=session, cache_root=cache_root, limit=1)

    assert first["created"] == 1
    assert second["created"] == 1
    assert third["created"] == 1
    assert second["exists"] == 0
    thumbnail_dir = cache_root / "thumbnails"
    created = {int(p.stem) for p in thumbnail_dir.glob("*.jpg")}
    assert created == set(asset_ids)


def test_build_pending_thumbnails_skips_non_image_assets(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(video),
            current_path=str(video),
            file_name=video.name,
            file_ext=".mp4",
            file_size=video.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()

    summary = build_pending_thumbnails(session=session, cache_root=tmp_path / ".cache", limit=5)

    assert summary["created"] == 0
    assert summary["skipped_non_image"] == 0


def test_ensure_thumbnail_reports_decompression_bomb_as_failed(tmp_path, monkeypatch):
    from PIL import Image
    import pims_v1.services.image_open_service as image_open_service

    session = make_session(tmp_path)
    source = tmp_path / "huge.jpg"
    Image.new("RGB", (8, 8), color="white").save(source)
    asset_row = add_asset(session, source)

    def raise_decompression_bomb(_path):
        raise Image.DecompressionBombWarning("too many pixels")

    monkeypatch.setattr(image_open_service.Image, "open", raise_decompression_bomb)

    result = ensure_thumbnail(session=session, asset_id=asset_row.id, cache_root=tmp_path / ".cache")

    assert result == {
        "asset_id": asset_row.id,
        "status": "failed",
        "path": None,
    }
