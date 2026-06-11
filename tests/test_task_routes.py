from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.api.tasks import get_session
from pims_v1.db import Base
from pims_v1.main import app
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.processing import ProcessingTask


def test_task_routes_list_and_recover_tasks(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    task = ProcessingTask(
        task_type="hash_md5",
        subject_type="asset",
        subject_id=1,
        status="running",
        attempts=1,
        heartbeat_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30),
    )
    session.add(task)
    session.commit()
    task_id = task.id
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

        recover_response = client.post("/tasks/recover", params={"stale_after_seconds": 300})
        list_response = client.get("/tasks", params={"status": "pending"})
    finally:
        app.dependency_overrides.clear()

    assert recover_response.status_code == 200
    assert recover_response.json() == {"recovered": 1}
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == task_id
    assert list_response.json()["items"][0]["status"] == "pending"
