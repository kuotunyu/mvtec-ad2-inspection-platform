from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import create_app


def test_health_and_job_contract() -> None:
    client = TestClient(create_app())
    health = client.get("/health/live")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    created = client.post("/api/jobs", json={"category": "can", "image_count": 2})
    assert created.status_code == 201
    payload = created.json()
    assert payload["category"] == "can"
    assert payload["status"] == "QUEUED"


def test_errors_use_stable_envelope() -> None:
    client = TestClient(create_app())
    response = client.get("/api/jobs/not-found")
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "request_id"}
