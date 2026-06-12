from fastapi.testclient import TestClient

from pims_v1.main import app


def test_healthcheck_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_progress_websocket_sends_snapshot():
    client = TestClient(app)

    with client.websocket_connect("/ws/progress") as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "snapshot"
    assert "progress" in payload
    assert "log" in payload
