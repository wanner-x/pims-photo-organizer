from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation
from pims_v1.models.series import Series, SeriesCandidate, SeriesSuggestion
from pims_v1.services.safe_workflow_service import run_safe_workflow


class StaticAIPlanClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def chat(self, messages):
        import json

        return json.dumps(self.payload, ensure_ascii=False)


class CountingAIPlanClient(StaticAIPlanClient):
    def __init__(self, payload: dict) -> None:
        super().__init__(payload)
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        return super().chat(messages)


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
        series_limit=100,
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

    def fake_notify(**kwargs) -> dict[str, int]:
        notifications.append(kwargs)
        return {"sent": 1, "failed": 0, "skipped": 0}

    monkeypatch.setattr("pims_v1.services.safe_workflow_service.notify_duplicate_approval_needed", fake_notify)
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
    assert summary["notification"] == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(notifications) == 1
    assert notifications[0]["batch_id"] == summary["duplicate_plan"]["batch_id"]
    assert notifications[0]["operations"] == 1


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


def test_run_safe_workflow_skips_similar_reviews_by_default(tmp_path, monkeypatch):
    from PIL import Image

    def fail_if_called(**kwargs):
        raise AssertionError("similar review building must be opt-in for long-running workflow")

    monkeypatch.setattr("pims_v1.services.safe_workflow_service.build_similar_image_reviews", fail_if_called)
    session = make_session(tmp_path)
    root = tmp_path / "library"
    root.mkdir()
    image_file = root / "a.jpg"
    Image.new("RGB", (16, 16), color="white").save(image_file)
    library_row = Library(name="Photos", kind="local", root_path=str(root))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(image_file),
            current_path=str(image_file),
            file_name=image_file.name,
            file_ext=image_file.suffix,
            file_size=image_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=None,
        cache_root=tmp_path / ".cache",
        md5_limit=1,
        phash_limit=1,
        thumbnail_limit=1,
        min_series_assets=1,
    )

    assert summary["similar"] == {"groups": 0, "review_items": 0, "skipped": 1}


def test_run_safe_workflow_skips_series_rebuild_by_default(tmp_path, monkeypatch):
    from PIL import Image

    def fail_if_called(**kwargs):
        raise AssertionError("series rebuild must be opt-in for long-running workflow")

    monkeypatch.setattr("pims_v1.services.safe_workflow_service.build_series_candidates", fail_if_called)
    session = make_session(tmp_path)
    root = tmp_path / "library"
    root.mkdir()
    image_file = root / "a.jpg"
    Image.new("RGB", (16, 16), color="white").save(image_file)
    library_row = Library(name="Photos", kind="local", root_path=str(root))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(image_file),
            current_path=str(image_file),
            file_name=image_file.name,
            file_ext=image_file.suffix,
            file_size=image_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=None,
        cache_root=tmp_path / ".cache",
        md5_limit=1,
        phash_limit=1,
        thumbnail_limit=1,
        min_series_assets=1,
    )

    assert summary["series"] == {"candidates": 0, "review_items": 0, "skipped": 1}


def test_run_safe_workflow_executes_batch_auto_archive_when_enabled(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    archive_root = tmp_path / "nas"
    source_dir = tmp_path / "pc" / "Alice" / "Alice Set [8P]"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color="white").save(source_file)

    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source_file),
            current_path=str(source_file),
            file_name=source_file.name,
            file_ext=source_file.suffix,
            file_size=source_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=str(archive_root),
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
        series_limit=100,
        auto_archive_limit=5,
        archive_client=StaticAIPlanClient(
            {
                "title": "Alice Set [8P]",
                "category": "Alice",
                "archive_path": "",
                "plan_summary": "keep person bucket",
                "risk_flags": [],
                "tags": [],
                "r18_label": False,
                "r18_confidence": 0.0,
                "r18_reason": "",
                "confidence": 0.93,
            }
        ),
    )

    assert summary["series"]["candidates"] == 1
    assert summary["archive_auto"]["processed"] == 1
    assert summary["archive_auto"]["auto_apply"] == 1
    assert summary["archive_auto"]["moved"] == 1
    assert session.query(Series).count() == 1


def test_run_safe_workflow_generates_ai_suggestions_when_enabled(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    archive_root = tmp_path / "nas"
    source_dir = tmp_path / "pc" / "Alice" / "Alice Set [8P]"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color="white").save(source_file)

    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source_file),
            current_path=str(source_file),
            file_name=source_file.name,
            file_ext=source_file.suffix,
            file_size=source_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=str(archive_root),
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
        series_limit=100,
        ai_suggest_limit=5,
        auto_archive_limit=0,
        archive_client=StaticAIPlanClient(
            {
                "title": "Alice Set [8P]",
                "category": "Alice",
                "archive_path": "",
                "plan_summary": "keep person bucket",
                "risk_flags": [],
                "tags": [],
                "r18_label": False,
                "r18_confidence": 0.0,
                "r18_reason": "",
                "confidence": 0.93,
            }
        ),
    )

    assert summary["ai_suggest"]["processed"] == 1
    assert summary["ai_suggest"]["suggested"] == 1
    assert session.query(SeriesSuggestion).count() == 1
    assert session.query(SeriesCandidate).one().status == "ai_suggested"


def test_run_safe_workflow_reuses_ai_suggestion_for_auto_archive(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    archive_root = tmp_path / "nas"
    source_dir = tmp_path / "pc" / "Alice" / "Alice Set [8P]"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color="white").save(source_file)

    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source_file),
            current_path=str(source_file),
            file_name=source_file.name,
            file_ext=source_file.suffix,
            file_size=source_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()
    client = CountingAIPlanClient(
        {
            "title": "Alice Set [8P]",
            "category": "Alice",
            "archive_path": "",
            "plan_summary": "keep person bucket",
            "risk_flags": [],
            "tags": [],
            "r18_label": False,
            "r18_confidence": 0.0,
            "r18_reason": "",
            "confidence": 0.93,
        }
    )

    summary = run_safe_workflow(
        session=session,
        keep_root=str(archive_root),
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
        series_limit=100,
        ai_suggest_limit=5,
        auto_archive_limit=5,
        archive_client=client,
    )

    assert summary["ai_suggest"]["suggested"] == 1
    assert summary["archive_auto"]["auto_apply"] == 1
    assert summary["archive_auto"]["moved"] == 1
    assert client.calls == 1
    assert session.query(Series).count() == 1
    assert session.query(SeriesSuggestion).one().status == "confirmed"


def test_run_safe_workflow_runs_r18_scan_before_auto_archive(tmp_path):
    from PIL import Image

    session = make_session(tmp_path)
    archive_root = tmp_path / "nas"
    source_dir = tmp_path / "pc" / "Alice" / "Alice Set [8P]"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "001.jpg"
    Image.new("RGB", (16, 16), color=(220, 180, 160)).save(source_file)

    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    session.add(
        Asset(
            library_id=library_row.id,
            original_path=str(source_file),
            current_path=str(source_file),
            file_name=source_file.name,
            file_ext=source_file.suffix,
            file_size=source_file.stat().st_size,
            mtime=1.0,
        )
    )
    session.commit()

    summary = run_safe_workflow(
        session=session,
        keep_root=str(archive_root),
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
        series_limit=100,
        r18_scan_limit=5,
        auto_archive_limit=5,
        archive_client=StaticAIPlanClient(
            {
                "title": "Alice Set [8P]",
                "category": "Alice",
                "archive_path": "",
                "plan_summary": "keep person bucket",
                "risk_flags": [],
                "tags": [],
                "r18_label": False,
                "r18_confidence": 0.0,
                "r18_reason": "",
                "confidence": 0.93,
            }
        ),
    )

    assert summary["r18_scan"]["processed"] == 1
    assert summary["r18_scan"]["flagged"] == 1
    assert summary["archive_auto"]["manual_review"] == 1
