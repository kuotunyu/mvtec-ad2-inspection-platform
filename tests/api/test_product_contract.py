from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from apps.api.main import create_app
from inspection_platform.settings import Settings


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (8, 8), "#4ca3af").save(stream, format="PNG")
    return stream.getvalue()


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
    )
    return TestClient(create_app(settings))


def test_upload_list_detail_cancel_and_artifact_are_database_scoped(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", ("part.png", _png(), "image/png"))],
    )
    assert created.status_code == 201
    job = created.json()
    assert job["status"] == "QUEUED"
    assert job["image_count"] == 1
    listed = client.get("/api/v1/jobs").json()
    assert [item["id"] for item in listed["items"]] == [job["id"]]
    detail = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert detail["images"][0]["filename"] == "part.png"
    artifact = client.get(detail["images"][0]["source_url"])
    assert artifact.content == _png()
    assert client.post(f"/api/v1/jobs/{job['id']}/cancel").json()["status"] == "CANCELLED"


def test_health_models_evidence_and_review_revision_contract(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/health/live").json()["status"] == "ok"
    assert client.get("/api/health/ready").json()["status"] == "ready"
    assert len(client.get("/api/v1/models").json()["items"]) == 8
    evidence = client.get("/api/v1/evidence").json()
    assert evidence["private_evaluation"] in {
        "not submitted",
        "local validator passed; official submission not performed",
    }
    assert evidence["serving_benchmark_status"] in {"not evaluated", "passed"}
    if evidence["serving_benchmark_status"] == "not evaluated":
        assert evidence["serving_benchmark_sha256"] is None

    created = client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", ("review.png", _png(), "image/png"))],
    ).json()
    image_id = client.get(f"/api/v1/jobs/{created['id']}").json()["images"][0]["id"]
    first = client.post(
        f"/api/v1/reviews/{image_id}",
        json={"decision": "UNCERTAIN", "note": "needs second look", "expected_revision": 0},
    )
    assert first.status_code == 201
    conflict = client.post(
        f"/api/v1/reviews/{image_id}",
        json={"decision": "REJECT", "expected_revision": 0},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "review_revision_conflict"
