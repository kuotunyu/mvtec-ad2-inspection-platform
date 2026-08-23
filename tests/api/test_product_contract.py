from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from threading import Barrier, Thread
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, event, func, select

from apps.api.main import create_app
from inspection_platform.db.models import (
    AuditEvent,
    InspectionImage,
    Job,
    Prediction,
    Review,
    WorkerHeartbeat,
)
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


def _seed_review_queue(
    client: TestClient,
    *,
    reviewed_count: int,
    pending_count: int,
    pass_count: int = 0,
) -> list[str]:
    now = datetime.now(UTC)
    job_id = "11111111-1111-1111-1111-111111111111"
    total = reviewed_count + pending_count + pass_count
    image_ids = [f"00000000-0000-0000-0000-{index:012d}" for index in range(total)]
    with client.app.state.sessions() as session, session.begin():
        session.add(
            Job(
                id=job_id,
                category="can",
                image_count=total,
                state="COMPLETED",
                created_at=now,
                attempt=1,
            )
        )
        session.flush()
        for index, image_id in enumerate(image_ids):
            session.add(
                InspectionImage(
                    id=image_id,
                    job_id=job_id,
                    artifact_key=f"artifact-{index}",
                    filename=f"item-{index}.png",
                    media_type="image/png",
                )
            )
        session.flush()
        for index, image_id in enumerate(image_ids):
            outcome = "PASS" if index >= reviewed_count + pending_count else "REVIEW"
            session.add(
                Prediction(
                    id=f"22222222-2222-2222-2222-{index:012d}",
                    image_id=image_id,
                    payload={
                        "anomaly_score": 1.0 if outcome == "REVIEW" else 0.0,
                        "model_outcome": outcome,
                        "threshold": 0.5,
                    },
                )
            )
        session.flush()
        for index, image_id in enumerate(image_ids[:reviewed_count]):
            session.add(
                Review(
                    id=f"33333333-3333-3333-3333-{index:012d}",
                    image_id=image_id,
                    decision="ACCEPT",
                    note=None,
                    created_at=now,
                    revision=1,
                )
            )
    return image_ids


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
    assert evidence["private_evaluation"] == "NO-GO under lighting shift"
    assert evidence["official_submission_performed"] is True
    assert evidence["serving_benchmark_status"] == "passed"
    serving = client.get(evidence["downloadable"]["serving_benchmark"])
    assert serving.status_code == 200
    assert evidence["serving_benchmark_sha256"] == hashlib.sha256(serving.content).hexdigest()
    official = client.get(evidence["downloadable"]["official_private_result"])
    assert official.status_code == 200
    assert official.json()["verdict"] == "PRIVATE-NO-GO"

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
    with client.app.state.sessions() as session:
        review_audits = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "review.recorded",
                AuditEvent.resource_id == image_id,
            )
        )
    assert review_audits == 1


def test_review_queue_filters_pending_items_before_page_limit(tmp_path: Path) -> None:
    client = _client(tmp_path)
    image_ids = _seed_review_queue(
        client,
        reviewed_count=100,
        pending_count=2,
        pass_count=1,
    )

    response = client.get("/api/v1/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == image_ids[100:102]


def test_review_queue_uses_bounded_queries_without_n_plus_one(tmp_path: Path) -> None:
    client = _client(tmp_path)
    pending_ids = _seed_review_queue(
        client,
        reviewed_count=1,
        pending_count=2,
        pass_count=1,
    )[1:3]
    engine = client.app.state.sessions.kw["bind"]
    assert isinstance(engine, Engine)
    select_statements: list[str] = []

    def record_select(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_select)
    try:
        payload = client.get("/api/v1/reviews").json()
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == pending_ids
    assert len(select_statements) <= 2


def test_concurrent_review_revisions_return_one_conflict(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", ("review.png", _png(), "image/png"))],
    ).json()
    image_id = client.get(f"/api/v1/jobs/{created['id']}").json()["images"][0]["id"]
    engine = client.app.state.sessions.kw["bind"]
    assert isinstance(engine, Engine)
    revisions_read = Barrier(2)

    def pause_after_revision_read(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "FROM reviews" in statement:
            revisions_read.wait(timeout=2)

    event.listen(engine, "after_cursor_execute", pause_after_revision_read)
    statuses: list[int] = []
    errors: list[Exception] = []

    def review(decision: str) -> None:
        try:
            response = client.post(
                f"/api/v1/reviews/{image_id}",
                json={"decision": decision, "expected_revision": 0},
            )
            statuses.append(response.status_code)
        except Exception as exc:
            errors.append(exc)

    reviewers = [Thread(target=review, args=(decision,)) for decision in ("ACCEPT", "REJECT")]
    for reviewer in reviewers:
        reviewer.start()
    for reviewer in reviewers:
        reviewer.join(timeout=5)
    event.remove(engine, "after_cursor_execute", pause_after_revision_read)

    assert errors == []
    assert sorted(statuses) == [201, 409]


def test_system_status_reports_persisted_worker_liveness_and_queue(tmp_path: Path) -> None:
    client = _client(tmp_path)
    initial = client.get("/api/v1/system/status")
    assert initial.status_code == 200
    assert initial.json()["worker_status"] == "missing"
    now = datetime.now(UTC)
    with client.app.state.sessions() as session, session.begin():
        session.add(
            WorkerHeartbeat(
                worker_id="worker-a",
                started_at=now,
                heartbeat_at=now,
                status="idle",
            )
        )
    client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", ("part.png", _png(), "image/png"))],
    )
    status = client.get("/api/v1/system/status").json()
    assert status["backend_status"] == "ready"
    assert status["worker_status"] == "current"
    assert status["active_queue"] == 1
    assert status["review_backlog"] == 0


def test_system_status_exposes_runtime_ingestion_limits(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        max_archive_files=7,
        max_upload_bytes=12_345,
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    assert response.json()["ingestion_limits"] == {
        "max_archive_files": 7,
        "max_upload_bytes": 12_345,
    }


def test_openapi_version_matches_stable_candidate_package(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.get("/openapi.json").json()["info"]["version"] == "0.1.0"
