from __future__ import annotations

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
