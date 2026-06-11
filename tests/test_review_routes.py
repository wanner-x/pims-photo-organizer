from fastapi.testclient import TestClient

from pims_v1.main import app


def test_review_routes_exist():
    client = TestClient(app)

    assert client.get("/libraries").status_code == 200
    assert client.get("/review/duplicates/exact").status_code == 200
    assert client.get("/operations/batches").status_code == 200
