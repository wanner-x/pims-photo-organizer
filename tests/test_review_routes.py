from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.api.operations import get_session
from pims_v1.api.review import get_session as get_review_session
from pims_v1.db import Base
from pims_v1.main import app
from pims_v1.models.asset import Asset
from pims_v1.models.duplicate import DuplicateGroup, DuplicateGroupAsset
from pims_v1.models.library import Library
from pims_v1.models.operation import Operation, OperationBatch


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


def test_operations_api_lists_batch_operations_with_asset_payload(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/a.jpg",
        current_path="/library/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=123,
        mtime=1.0,
        hash_md5="same",
    )
    session.add(asset_row)
    session.flush()
    batch = OperationBatch(batch_type="duplicate_quarantine", status="planned")
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
                "file_size": 123,
                "hash_md5": "same",
                "hash_phash": None,
                "thumbnail_url": f"/thumbnails/{asset_id}.jpg",
            },
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
