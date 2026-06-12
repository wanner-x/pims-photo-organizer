from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation
from pims_v1.models.series import SeriesCandidate
from pims_v1.services.safe_workflow_service import run_safe_workflow


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_run_safe_workflow_builds_candidates_and_duplicate_plan(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    local_root = tmp_path / "pc"
    nas_root = tmp_path / "nas"
    local_root.mkdir()
    nas_root.mkdir()
    local_file = local_root / "a.jpg"
    nas_file = nas_root / "a.jpg"
    Image.new("RGB", (16, 16), color="white").save(local_file)
    nas_file.write_bytes(local_file.read_bytes())
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    session.add_all(
        [
            Asset(
                library_id=library_row.id,
                original_path=str(local_file),
                current_path=str(local_file),
                file_name="a.jpg",
                file_ext=".jpg",
                file_size=local_file.stat().st_size,
                mtime=1.0,
            ),
            Asset(
                library_id=library_row.id,
                original_path=str(nas_file),
                current_path=str(nas_file),
                file_name="a.jpg",
                file_ext=".jpg",
                file_size=nas_file.stat().st_size,
                mtime=1.0,
            ),
        ]
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=str(nas_root),
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
    )

    assert summary["md5"]["processed"] == 2
    assert summary["phash"]["processed"] == 2
    assert summary["duplicates"]["groups"] == 1
    assert summary["series"]["candidates"] == 2
    assert summary["thumbnails"]["created"] == 2
    assert summary["duplicate_plan"]["operations"] == 1
    assert session.query(DuplicateGroup).count() == 1
    assert session.query(SeriesCandidate).count() == 2
    assert session.query(Operation).one().from_path == str(local_file)


def test_run_safe_workflow_notifies_when_duplicate_plan_needs_approval(tmp_path, monkeypatch):
    from PIL import Image

    notifications = []

    def fake_send_message(webhook_url: str, content: str) -> dict[str, int | str]:
        notifications.append({"webhook_url": webhook_url, "content": content})
        return {"ok": 1}

    monkeypatch.setattr("pims_v1.services.safe_workflow_service.send_wechat_text_message", fake_send_message)
    monkeypatch.setattr(
        "pims_v1.services.safe_workflow_service.settings.wechat_webhook_url",
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
    )

    session = make_session(tmp_path)
    local_root = tmp_path / "pc"
    nas_root = tmp_path / "nas"
    local_root.mkdir()
    nas_root.mkdir()
    local_file = local_root / "a.jpg"
    nas_file = nas_root / "a.jpg"
    Image.new("RGB", (16, 16), color="white").save(local_file)
    nas_file.write_bytes(local_file.read_bytes())
    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    session.add_all(
        [
            Asset(
                library_id=library_row.id,
                original_path=str(local_file),
                current_path=str(local_file),
                file_name="a.jpg",
                file_ext=".jpg",
                file_size=local_file.stat().st_size,
                mtime=1.0,
            ),
            Asset(
                library_id=library_row.id,
                original_path=str(nas_file),
                current_path=str(nas_file),
                file_name="a.jpg",
                file_ext=".jpg",
                file_size=nas_file.stat().st_size,
                mtime=1.0,
            ),
        ]
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=str(nas_root),
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
    )

    assert summary["duplicate_plan"]["operations"] == 1
    assert summary["notification"] == {"sent": 1, "failed": 0}
    assert len(notifications) == 1
    assert "需要批量审批" in notifications[0]["content"]
    assert "批次" in notifications[0]["content"]


def test_run_safe_workflow_only_enqueues_images_for_phash(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    root = tmp_path / "library"
    root.mkdir()
    image_file = root / "a.jpg"
    video_file = root / "clip.mp4"
    Image.new("RGB", (16, 16), color="white").save(image_file)
    video_file.write_bytes(b"video")
    library_row = Library(name="Photos", kind="local", root_path=str(root))
    session.add(library_row)
    session.flush()
    session.add_all(
        [
            Asset(
                library_id=library_row.id,
                original_path=str(image_file),
                current_path=str(image_file),
                file_name="a.jpg",
                file_ext=".jpg",
                file_size=image_file.stat().st_size,
                mtime=1.0,
            ),
            Asset(
                library_id=library_row.id,
                original_path=str(video_file),
                current_path=str(video_file),
                file_name="clip.mp4",
                file_ext=".mp4",
                file_size=video_file.stat().st_size,
                mtime=1.0,
            ),
        ]
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=None,
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
    )

    assert summary["phash_enqueued"]["queued"] == 1
    assert summary["phash"]["processed"] == 1
    assert summary["phash"]["skipped_non_image"] == 0
