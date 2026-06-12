from fastapi.testclient import TestClient

import pims_v1.main as main_module
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


def test_progress_websocket_stays_open_after_snapshot_error(monkeypatch):
    calls = {"count": 0}

    def flaky_snapshot():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("database is locked")
        return {"type": "snapshot", "progress": {"ok": True}, "log": {"found": False}}

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr(main_module, "_progress_snapshot", flaky_snapshot)
    monkeypatch.setattr(main_module.asyncio, "sleep", fast_sleep)
    client = TestClient(app)

    with client.websocket_connect("/ws/progress") as websocket:
        error_payload = websocket.receive_json()
        snapshot_payload = websocket.receive_json()

    assert error_payload == {
        "type": "error",
        "message": "自动刷新暂时失败，正在继续重试。",
    }
    assert snapshot_payload["type"] == "snapshot"
