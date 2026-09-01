from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_returns_service_status():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "Revenue Recovery Control Plane",
        "environment": "development",
        "status": "ok",
        "version": "0.2.0-phase1",
    }


def test_live_endpoint_matches_liveness_contract():
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
