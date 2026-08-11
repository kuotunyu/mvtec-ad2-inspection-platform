from __future__ import annotations

from pytest import MonkeyPatch

from inspection_platform.db.repositories import JobRepository

from .conftest import SystemHarness


def test_batch_partial_success_review_and_report(system_harness: SystemHarness) -> None:
    created = system_harness.upload("clean-control.png", "scratch-review.png", corrupt=True)
    assert system_harness.worker.process_once()
    detail = system_harness.client.get(f"/api/v1/jobs/{created['id']}").json()
    assert detail["status"] == "COMPLETED_WITH_ERRORS"
    assert detail["completed_count"] == 2
    assert detail["error_count"] == 1
    assert {item["model_outcome"] for item in detail["images"] if not item["error"]} == {
        "PASS",
        "REVIEW",
    }
    completed = next(item for item in detail["images"] if not item["error"])
    assert completed["anomaly_map_url"] != completed["source_url"]
    assert completed["overlay_url"] != completed["source_url"]
    assert len(completed["anomaly_map_sha256"]) == 64
    assert len(completed["overlay_sha256"]) == 64
    anomaly_response = system_harness.client.get(completed["anomaly_map_url"])
    overlay_response = system_harness.client.get(completed["overlay_url"])
    assert anomaly_response.status_code == 200
    assert overlay_response.status_code == 200
    assert anomaly_response.headers["content-type"] == "image/png"
    assert overlay_response.headers["content-type"] == "image/png"
    assert anomaly_response.content != overlay_response.content
    system_status = system_harness.client.get("/api/v1/system/status").json()
    assert system_status["worker_status"] == "current"
    assert system_status["active_queue"] == 0
    assert system_status["review_backlog"] == 1
    review_item = next(item for item in detail["images"] if item["model_outcome"] == "REVIEW")
    reviewed = system_harness.client.post(
        f"/api/v1/reviews/{review_item['id']}",
        json={"decision": "ACCEPT", "note": "synthetic test", "expected_revision": 0},
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["revision"] == 1
    report = system_harness.client.get(f"/api/v1/jobs/{created['id']}/report.json")
    assert report.status_code == 200
    assert report.json()["job"]["id"] == created["id"]
    assert len(report.headers["x-content-sha256"]) == 64


def test_upload_does_not_publish_a_claimable_job_before_images_commit(
    system_harness: SystemHarness, monkeypatch: MonkeyPatch
) -> None:
    original_create = JobRepository.create
    premature_claims: list[bool] = []

    def create_then_poll(repository: JobRepository, *, category: str, image_count: int) -> object:
        job = original_create(repository, category=category, image_count=image_count)
        premature_claims.append(system_harness.worker.process_once())
        return job

    monkeypatch.setattr(JobRepository, "create", create_then_poll)
    created = system_harness.upload("clean-control.png")
    detail = system_harness.client.get(f"/api/v1/jobs/{created['id']}").json()

    assert premature_claims == []
    assert detail["status"] == "QUEUED"
    assert len(detail["images"]) == 1
