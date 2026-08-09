from __future__ import annotations

import hashlib

from .conftest import SystemHarness


def test_report_downloads_are_deterministic_and_byte_valid(
    system_harness: SystemHarness,
) -> None:
    created = system_harness.upload("clean-control.png", "dent-review.png")
    system_harness.worker.process_once()
    for extension, media_type in (
        ("json", "application/json"),
        ("csv", "text/csv"),
        ("html", "text/html"),
    ):
        first = system_harness.client.get(f"/api/v1/jobs/{created['id']}/report.{extension}")
        second = system_harness.client.get(f"/api/v1/jobs/{created['id']}/report.{extension}")
        assert first.status_code == 200
        assert first.content == second.content
        assert first.headers["content-type"].startswith(media_type)
        assert first.headers["x-content-sha256"] == hashlib.sha256(first.content).hexdigest()
        assert b"C:\\" not in first.content and b"/Users/" not in first.content
