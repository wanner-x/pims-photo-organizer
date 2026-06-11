from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.api.operations import get_session
from pims_v1.db import Base
from pims_v1.main import app
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

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)

        response = client.post(
            f"/operations/batches/{batch_id}/execute",
            params={"quarantine_root": str(tmp_path / ".quarantine")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "batch_id": batch_id,
        "executed": 1,
        "failed": 0,
        "status": "executed",
    }
    assert not source.exists()
