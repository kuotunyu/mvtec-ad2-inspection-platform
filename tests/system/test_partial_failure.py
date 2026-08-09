from __future__ import annotations

from .conftest import SystemHarness


def test_missing_artifact_fails_one_image_closed(system_harness: SystemHarness) -> None:
    created = system_harness.upload("clean-control.png")
    for artifact in system_harness.settings.artifact_root.rglob("*"):
        if artifact.is_file():
            artifact.unlink()
    system_harness.worker.process_once()
    detail = system_harness.client.get(f"/api/v1/jobs/{created['id']}").json()
    assert detail["status"] == "COMPLETED_WITH_ERRORS"
    assert detail["images"][0]["error"] == "inference_failed"


def test_tampered_bundle_fails_job_closed(system_harness: SystemHarness) -> None:
    created = system_harness.upload("clean-control.png")
    payload = system_harness.settings.model_registry_root / "categories/can/mock.json"
    payload.write_text("tampered", encoding="utf-8")
    system_harness.worker.process_once()
    detail = system_harness.client.get(f"/api/v1/jobs/{created['id']}").json()
    assert detail["status"] == "FAILED"
    assert detail["images"][0]["error"] == "bundle_integrity_failed"
