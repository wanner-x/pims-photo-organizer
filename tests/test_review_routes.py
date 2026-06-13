from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.api.operations import get_session
import pims_v1.api.progress as progress_api
import pims_v1.api.review as review_api
from pims_v1.api.review import get_session as get_review_session
from pims_v1.api.progress import get_session as get_progress_session
from pims_v1.db import Base
from pims_v1.main import app
from pims_v1.main import get_session as get_media_session
from pims_v1.models.archive_decision import ArchiveExecutionRecord, ArchivePlanningRecord, ArchiveRiskEvent
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation, OperationBatch
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.models.series_moderation import SeriesModerationRun


def test_review_routes_exist():
    client = TestClient(app)

    assert client.get("/libraries").status_code == 200
    assert client.get("/review/duplicates/exact").status_code == 200
    assert client.get("/operations/batches").status_code == 200


def test_operations_api_lists_and_confirms_batches(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="planned")
    session.add(batch)
    session.flush()
    session.add(
        Operation(
            batch_id=batch.id,
            operation_type="quarantine_duplicate",
            from_path="D:\\photos\\a.jpg",
            status="planned",
        )
    )
    session.commit()
    batch_id = batch.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)

        list_response = client.get("/operations/batches")
        confirm_response = client.post(f"/operations/batches/{batch_id}/confirm")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["operation_count"] == 1
    assert confirm_response.status_code == 200
    assert confirm_response.json() == {
        "batch_id": batch_id,
        "operations": 1,
        "status": "confirmed",
    }

    session = session_factory()
    assert session.get(OperationBatch, batch_id).status == "confirmed"


def test_operations_api_executes_confirmed_batch(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    source = tmp_path / "library" / "a.jpg"
    source.parent.mkdir()
    source.write_bytes(b"duplicate")
    session = session_factory()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="confirmed")
    session.add(batch)
    session.flush()
    session.add(
        Operation(
            batch_id=batch.id,
            operation_type="quarantine_duplicate",
            from_path=str(source),
            status="confirmed",
        )
    )
    session.commit()
    batch_id = batch.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    quarantine_root = tmp_path / ".configured-quarantine"
    app.dependency_overrides[get_session] = override_get_session
    try:
        import pims_v1.api.operations as operations_api

        old_quarantine_root = operations_api.settings.quarantine_root
        operations_api.settings.quarantine_root = str(quarantine_root)
        client = TestClient(app)

        response = client.post(f"/operations/batches/{batch_id}/execute")
    finally:
        operations_api.settings.quarantine_root = old_quarantine_root
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "batch_id": batch_id,
        "executed": 1,
        "failed": 0,
        "status": "executed",
    }
    assert not source.exists()
    assert (quarantine_root / "a.jpg").exists()


def test_operations_api_requires_token_when_configured(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        import pims_v1.api.operations as operations_api

        old_token = operations_api.settings.api_token
        operations_api.settings.api_token = "secret"
        client = TestClient(app)

        unauthorized = client.post("/operations/batches/1/confirm")
        authorized = client.post(
            "/operations/batches/1/confirm",
            headers={"x-pims-api-token": "secret"},
        )
    finally:
        operations_api.settings.api_token = old_token
        app.dependency_overrides.clear()

    assert unauthorized.status_code == 401
    assert authorized.status_code == 400


def test_operations_api_excludes_planned_operation(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="planned")
    session.add(batch)
    session.flush()
    operation = Operation(
        batch_id=batch.id,
        operation_type="quarantine_duplicate",
        from_path="D:\\photos\\a.jpg",
        status="planned",
    )
    session.add(operation)
    session.commit()
    operation_id = operation.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.post(f"/operations/{operation_id}/exclude")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"operation_id": operation_id, "status": "excluded"}


def test_review_ui_page_exists():
    client = TestClient(app)

    response = client.get("/review-ui")

    assert response.status_code == 200
    assert "PIMS Review" in response.text
    assert "待确认隔离批次" in response.text
    assert "整理进度" in response.text
    assert "已存在位置" in response.text
    assert "重复位置" in response.text
    assert "/ws/progress" in response.text
    assert "preview-modal" in response.text
    assert "openPreview" in response.text
    assert "AI 系列整理审核" in response.text
    assert "确认并移动到 NAS" in response.text
    assert "批量生成 AI 建议" in response.text
    assert "批量确认并移动" in response.text
    assert "selectedSeriesIds" in response.text
    assert "withButtonLoading" in response.text
    assert "series-busy" in response.text
    assert "aria-busy" in response.text
    assert "首个错误" in response.text
    assert "目标路径" in response.text
    assert "content-tags" in response.text
    assert "plan-summary" in response.text
    assert "risk-flags" in response.text
    assert "rule-plan" in response.text
    assert "series-filter" in response.text
    assert "needs_ai" in response.text
    assert "target_conflict" in response.text
    assert "审核功能导航" in response.text
    assert "data-view-target=\"series\"" in response.text
    assert "data-view-panel=\"duplicates\"" in response.text
    assert "AI 系列整理" in response.text
    assert "重复隔离审核" in response.text


def test_review_ui_inline_video_preview_does_not_show_player_controls():
    client = TestClient(app)

    response = client.get("/review-ui")

    assert response.status_code == 200
    assert "video.muted = true;" in response.text
    assert "video.playsInline = true;" in response.text
    assert "video.pause();" in response.text


def test_review_ui_handles_progress_socket_error_payload():
    client = TestClient(app)

    response = client.get("/review-ui")

    assert response.status_code == 200
    assert 'payload.type === "error"' in response.text
    assert "payload.message" in response.text


def test_review_ui_includes_mobile_adaptation_rules():
    client = TestClient(app)

    response = client.get("/review-ui")

    assert response.status_code == 200
    assert "@media (max-width: 720px)" in response.text
    assert "position: sticky" in response.text
    assert "top: 74px" in response.text
    assert "bottom: 12px" not in response.text
    assert "grid-template-columns: 1fr" in response.text
    assert "overflow-x: hidden" in response.text


def test_review_ui_includes_archive_anomaly_and_ledger_views():
    client = TestClient(app)

    response = client.get("/review-ui")

    assert response.status_code == 200
    assert 'data-view-target="archive"' in response.text
    assert 'data-view-target="sampling"' in response.text
    assert 'data-view-target="anomalies"' in response.text
    assert 'data-view-target="ledger"' in response.text
    assert "loadArchiveOverview" in response.text
    assert "loadArchiveSampling" in response.text
    assert "loadArchiveAnomalies" in response.text
    assert "loadArchiveLedger" in response.text
    assert "rollbackExecution" in response.text
    assert "scan-r18" in response.text
    assert "moderation-provider" in response.text


def test_operations_api_lists_batch_operations_with_asset_payload(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    local_library = Library(name="Local", kind="local", root_path="/library")
    nas_library = Library(name="NAS", kind="nas", root_path="/nas")
    session.add_all([local_library, nas_library])
    session.flush()
    asset_row = Asset(
        library_id=local_library.id,
        original_path="/library/a.jpg",
        current_path="/library/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=123,
        mtime=1.0,
        hash_md5="same",
    )
    keep_asset = Asset(
        library_id=nas_library.id,
        original_path="/nas/a.jpg",
        current_path="/nas/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=123,
        mtime=1.0,
        hash_md5="same",
    )
    session.add_all([asset_row, keep_asset])
    session.flush()
    batch = OperationBatch(
        batch_type="duplicate_quarantine",
        status="planned",
        description="Keep copies under /nas; quarantine duplicate copies elsewhere.",
    )
    session.add(batch)
    session.flush()
    operation = Operation(
        batch_id=batch.id,
        operation_type="quarantine_duplicate",
        asset_id=asset_row.id,
        from_path="/library/a.jpg",
        status="planned",
    )
    session.add(operation)
    session.commit()
    batch_id = batch.id
    operation_id = operation.id
    asset_id = asset_row.id
    keep_asset_id = keep_asset.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get(f"/operations/batches/{batch_id}/operations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 200
    assert payload["offset"] == 0
    assert payload["items"] == [
        {
            "id": operation_id,
            "batch_id": batch_id,
            "operation_type": "quarantine_duplicate",
            "status": "planned",
            "from_path": "/library/a.jpg",
            "to_path": None,
            "asset": {
                "id": asset_id,
                "file_name": "a.jpg",
                "current_path": "/library/a.jpg",
                "file_ext": ".jpg",
                "file_size": 123,
                "hash_md5": "same",
                "hash_phash": None,
                "media_url": f"/media/assets/{asset_id}",
                "thumbnail_url": f"/thumbnails/{asset_id}.jpg",
            },
            "duplicate_assets": [
                {
                    "id": asset_id,
                    "file_name": "a.jpg",
                    "current_path": "/library/a.jpg",
                    "file_ext": ".jpg",
                    "file_size": 123,
                    "hash_md5": "same",
                    "hash_phash": None,
                    "library_kind": "local",
                    "media_url": f"/media/assets/{asset_id}",
                    "role": "duplicate_target",
                    "role_label": "重复位置，将隔离",
                    "thumbnail_url": f"/thumbnails/{asset_id}.jpg",
                },
                {
                    "id": keep_asset_id,
                    "file_name": "a.jpg",
                    "current_path": "/nas/a.jpg",
                    "file_ext": ".jpg",
                    "file_size": 123,
                    "hash_md5": "same",
                    "hash_phash": None,
                    "library_kind": "nas",
                    "media_url": f"/media/assets/{keep_asset_id}",
                    "role": "keep_copy",
                    "role_label": "已存在位置，建议保留",
                    "thumbnail_url": f"/thumbnails/{keep_asset_id}.jpg",
                },
            ],
        }
    ]


def test_thumbnail_route_serves_cached_thumbnail(tmp_path):
    thumbnail_dir = tmp_path / ".cache" / "thumbnails"
    thumbnail_dir.mkdir(parents=True)
    (thumbnail_dir / "7.jpg").write_bytes(b"jpeg")

    import pims_v1.main as main_module

    old_cache_root = main_module.settings.cache_root
    main_module.settings.cache_root = str(tmp_path / ".cache")
    try:
        client = TestClient(app)
        response = client.get("/thumbnails/7.jpg")
    finally:
        main_module.settings.cache_root = old_cache_root

    assert response.status_code == 200
    assert response.content == b"jpeg"


def test_media_route_serves_video_asset(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Videos", kind="local", root_path=str(tmp_path))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(video),
        current_path=str(video),
        file_name="clip.mp4",
        file_ext=".mp4",
        file_size=5,
        mtime=1.0,
    )
    session.add(asset_row)
    session.commit()
    asset_id = asset_row.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_media_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get(f"/media/assets/{asset_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"video"


def test_progress_summary_api_reports_overall_progress(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    session.add_all(
        [
            Asset(
                library_id=library_row.id,
                original_path="/library/a.jpg",
                current_path="/library/a.jpg",
                file_name="a.jpg",
                file_ext=".jpg",
                file_size=1,
                mtime=1.0,
                hash_md5="a",
                hash_phash="ff",
            ),
            Asset(
                library_id=library_row.id,
                original_path="/library/b.mp4",
                current_path="/library/b.mp4",
                file_name="b.mp4",
                file_ext=".mp4",
                file_size=1,
                mtime=1.0,
            ),
        ]
    )
    session.commit()
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_progress_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/progress/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["assets"] == {
        "total": 2,
        "md5_done": 1,
        "md5_percent": 50.0,
        "phash_done": 1,
        "phash_total": 1,
        "phash_percent": 100.0,
    }


def test_progress_latest_log_api_returns_tail_lines(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old_log = log_dir / "full-detection-20260612-010000.log"
    new_log = log_dir / "full-detection-20260612-020000.log"
    old_log.write_text("old\n", encoding="utf-8")
    new_log.write_text("one\ntwo\nthree\n", encoding="utf-8")

    old_logs_root = progress_api.settings.logs_root
    progress_api.settings.logs_root = str(log_dir)
    try:
        client = TestClient(app)
        response = client.get("/progress/logs/latest", params={"lines": 2})
    finally:
        progress_api.settings.logs_root = old_logs_root

    assert response.status_code == 200
    assert response.json() == {
        "found": True,
        "name": "full-detection-20260612-020000.log",
        "lines": ["two", "three"],
    }


def test_progress_latest_log_api_reads_utf16_powershell_logs(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "full-detection-20260612-030000.log"
    log_file.write_text("进度一\nprogress.hash_md5.seen=100\n", encoding="utf-16")

    old_logs_root = progress_api.settings.logs_root
    progress_api.settings.logs_root = str(log_dir)
    try:
        client = TestClient(app)
        response = client.get("/progress/logs/latest", params={"lines": 1})
    finally:
        progress_api.settings.logs_root = old_logs_root

    assert response.status_code == 200
    assert response.json()["lines"] == ["progress.hash_md5.seen=100"]


def test_review_api_lists_exact_duplicate_groups(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = Asset(
        library_id=library_row.id,
        original_path="/library/a.jpg",
        current_path="/library/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
        hash_md5="same",
    )
    second = Asset(
        library_id=library_row.id,
        original_path="/library/b.jpg",
        current_path="/library/b.jpg",
        file_name="b.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
        hash_md5="same",
    )
    session.add_all([first, second])
    session.flush()
    group = DuplicateGroup(hash_md5="same", asset_count=2)
    session.add(group)
    session.flush()
    session.add_all(
        [
            DuplicateGroupAsset(group_id=group.id, asset_id=first.id),
            DuplicateGroupAsset(group_id=group.id, asset_id=second.id),
        ]
    )
    session.commit()
    group_id = group.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/review/duplicates/exact", params={"thumbnail_base": "/thumbs"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == group_id
    assert payload["items"][0]["assets"][0]["thumbnail_url"].startswith("/thumbs/")


def test_review_series_suggest_ai_api_creates_pending_suggestion(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set", title="set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def chat(self, messages):
            return (
                '{"title":"清晨写真","category":"写真合集","confidence":0.7,'
                '"plan_summary":"移动到 NAS 归档目录","risk_flags":["人工复核"],'
                '"tags":["R18"],"r18_label":true,"r18_confidence":0.8,"r18_reason":"测试标签"}'
            )

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    monkeypatch.setattr("pims_v1.api.review.DeepSeekClient", FakeClient)
    monkeypatch.setattr("pims_v1.api.review.settings.deepseek_api_key", "test-key")
    monkeypatch.setattr("pims_v1.api.review.settings.keep_root", str(tmp_path / "nas"))
    try:
        client = TestClient(app)
        response = client.post(f"/review/series/{candidate_id}/suggest-ai")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["title"] == "清晨写真 [R18]"
    assert response.json()["archive_path"].endswith("写真合集\\清晨写真 [R18]") or response.json()["archive_path"].endswith("写真合集/清晨写真 [R18]")
    assert response.json()["plan_summary"] == "移动到 NAS 归档目录"
    assert response.json()["risk_flags"] == ["人工复核"]
    assert response.json()["tags"] == ["R18"]
    assert response.json()["r18_label"] is True
    assert response.json()["r18_confidence"] == 0.8
    assert response.json()["r18_reason"] == "测试标签"
    session = session_factory()
    assert session.query(SeriesSuggestion).one().status == "pending_review"


def test_review_series_api_filters_needs_ai_candidates(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    first = SeriesCandidate(library_id=library_row.id, source_root="/library/needs-ai", title="needs-ai")
    second = SeriesCandidate(library_id=library_row.id, source_root="/library/has-ai", title="has-ai", status="ai_suggested")
    session.add_all([first, second])
    session.flush()
    session.add(
        SeriesSuggestion(
            candidate_id=second.id,
            suggested_title="Has AI",
            suggested_category="People",
            confidence=0.9,
            status="pending_review",
        )
    )
    session.commit()
    first_id = first.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/review/series", params={"filter": "needs_ai"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [first_id]


def test_review_series_confirm_suggestion_api_moves_assets_to_keep_root(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    source_root = tmp_path / "pc" / "set"
    source_root.mkdir(parents=True)
    source_file = source_root / "a.jpg"
    source_file.write_bytes(b"image")
    archive_root = tmp_path / "nas"
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source_file),
        current_path=str(source_file),
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=source_file.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root=str(source_root), title="set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.flush()
    suggestion = SeriesSuggestion(
        candidate_id=candidate.id,
        suggested_title="清晨写真",
        suggested_category="写真合集",
        confidence=0.8,
        status="pending_review",
    )
    session.add(suggestion)
    session.commit()
    suggestion_id = suggestion.id
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    monkeypatch.setattr(review_api.settings, "keep_root", str(archive_root))
    try:
        client = TestClient(app)
        response = client.post(f"/review/series-suggestions/{suggestion_id}/confirm")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["moved"] == 1
    assert not source_file.exists()
    assert (archive_root / "写真合集" / "清晨写真" / "a.jpg").exists()


def test_review_auto_archive_series_api_executes_dual_engine_archive(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    source_root = tmp_path / "pc" / "set"
    source_root.mkdir(parents=True)
    source_file = source_root / "a.jpg"
    source_file.write_bytes(b"image")
    archive_root = tmp_path / "nas"
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source_file),
        current_path=str(source_file),
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=source_file.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]",
        title="雪琪SAMA 透明女仆 [43P4V234MB]",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def chat(self, messages):
            return (
                '{"title":"雪琪SAMA 透明女仆 [43P4V234MB]","category":"雪琪SAMA",'
                '"archive_path":"","plan_summary":"保持人物目录结构","risk_flags":[],'
                '"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.93}'
            )

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    monkeypatch.setattr("pims_v1.api.review.DeepSeekClient", FakeClient)
    monkeypatch.setattr(review_api.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(review_api.settings, "keep_root", str(archive_root))
    try:
        client = TestClient(app)
        response = client.post(f"/review/series/{candidate_id}/auto-archive")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["decision_type"] == "auto_apply"
    assert response.json()["status"] == "confirmed"
    assert (archive_root / "雪琪SAMA" / "雪琪SAMA 透明女仆 [43P4V234MB]" / "a.jpg").exists()


def test_review_series_scan_r18_api_persists_latest_moderation(tmp_path, monkeypatch):
    from PIL import Image

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    source_root = tmp_path / "pc" / "set"
    source_root.mkdir(parents=True)
    source_file = source_root / "a.jpg"
    Image.new("RGB", (16, 16), color=(220, 180, 160)).save(source_file)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source_file),
        current_path=str(source_file),
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=source_file.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root=str(source_root), title="set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    class FakeVisualClient:
        provider_name = "static"

        def moderate_image(self, path):
            return {"label": "nsfw_suspected", "score": 0.91, "reason": "test", "provider": self.provider_name}

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    monkeypatch.setattr("pims_v1.api.review.build_visual_moderation_client", lambda provider_name="auto": FakeVisualClient())
    try:
        client = TestClient(app)
        response = client.post(f"/review/series/{candidate_id}/scan-r18")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["r18_label"] is True
    session = session_factory()
    assert session.query(SeriesModerationRun).one().flagged_samples == 1


def test_review_archive_overview_api_returns_planning_and_execution_counts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set", title="set", status="confirmed")
    session.add(candidate)
    session.flush()
    planning = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json="{}",
        ai_plan_json="{}",
        final_plan_json='{"title":"set"}',
        decision_type="auto_apply",
        rule_score=0.9,
        ai_score=0.9,
        risk_score=0.0,
        decision_reason="agreed",
    )
    session.add(planning)
    session.flush()
    session.add(
        ArchiveExecutionRecord(
            planning_record_id=planning.id,
            operation_type="archive_move",
            source_path="/library/set/a.jpg",
            target_path="/nas/set/a.jpg",
            status="done",
        )
    )
    session.commit()
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/review/archive/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["planning"]["auto_apply"] == 1
    assert response.json()["executions"]["done"] == 1


def test_review_archive_anomalies_api_returns_risk_events(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/r18", title="r18", status="pending_review")
    session.add(candidate)
    session.flush()
    planning = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json="{}",
        ai_plan_json="{}",
        final_plan_json='{"title":"r18"}',
        decision_type="manual_review",
        rule_score=0.9,
        ai_score=0.9,
        risk_score=1.0,
        decision_reason="r18 suspected",
    )
    session.add(planning)
    session.flush()
    session.add(
        ArchiveRiskEvent(
            planning_record_id=planning.id,
            event_type="r18_suspected",
            severity="warning",
            details_json='{"source":"ai"}',
        )
    )
    session.commit()
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/review/archive/anomalies")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["event_type"] == "r18_suspected"


def test_review_archive_sampling_api_returns_sampled_items(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set", title="set", status="confirmed")
    session.add(candidate)
    session.flush()
    planning = ArchivePlanningRecord(
        candidate_id=candidate.id,
        source_root=candidate.source_root,
        rule_plan_json="{}",
        ai_plan_json="{}",
        final_plan_json='{"title":"set"}',
        decision_type="auto_apply_sampled",
        rule_score=0.95,
        ai_score=0.85,
        risk_score=0.25,
        decision_reason="sample review recommended",
    )
    session.add(planning)
    session.flush()
    session.add(
        ArchiveRiskEvent(
            planning_record_id=planning.id,
            event_type="sample_review_recommended",
            severity="warning",
            details_json='{"reason":"title difference"}',
        )
    )
    session.commit()
    session.close()

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/review/archive/sampling")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["decision_type"] == "auto_apply_sampled"


def test_review_archive_rollback_api_restores_file(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    source_root = tmp_path / "pc" / "set"
    source_root.mkdir(parents=True)
    source_file = source_root / "a.jpg"
    source_file.write_bytes(b"image")
    archive_root = tmp_path / "nas"
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(source_file),
        current_path=str(source_file),
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=source_file.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]",
        title="雪琪SAMA 透明女仆 [43P4V234MB]",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    candidate_id = candidate.id
    session.close()

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def chat(self, messages):
            return (
                '{"title":"雪琪SAMA 透明女仆 [43P4V234MB]","category":"雪琪SAMA",'
                '"archive_path":"","plan_summary":"保持人物目录结构","risk_flags":[],'
                '"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.93}'
            )

    def override_get_session():
        test_session = session_factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_review_session] = override_get_session
    monkeypatch.setattr("pims_v1.api.review.DeepSeekClient", FakeClient)
    monkeypatch.setattr(review_api.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(review_api.settings, "keep_root", str(archive_root))
    try:
        client = TestClient(app)
        auto_response = client.post(f"/review/series/{candidate_id}/auto-archive")
        execution_id = auto_response.json()["execution_ids"][0]
        rollback_response = client.post(f"/review/archive/executions/{execution_id}/rollback")
    finally:
        app.dependency_overrides.clear()

    assert rollback_response.status_code == 200
    assert rollback_response.json()["status"] == "rolled_back"
    assert source_file.exists()
