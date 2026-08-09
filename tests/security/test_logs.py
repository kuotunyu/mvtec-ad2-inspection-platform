from __future__ import annotations

import logging

from pytest import LogCaptureFixture

from tests.system.conftest import SystemHarness


def test_worker_failure_log_contains_only_stable_identifiers(
    system_harness: SystemHarness, caplog: LogCaptureFixture
) -> None:
    created = system_harness.upload("clean-control.png")
    bundle = system_harness.settings.model_registry_root / "categories/can/mock.json"
    bundle.write_text("private raw exception detail", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        system_harness.worker.process_once()
    text = caplog.text
    assert "job failed" in text
    assert str(system_harness.root) not in text
    assert "private raw exception detail" not in text
    assert "Traceback" not in text
    detail = system_harness.client.get(f"/api/v1/jobs/{created['id']}").text
    assert str(system_harness.root) not in detail
