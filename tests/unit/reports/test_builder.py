from __future__ import annotations

from inspection_platform.reports.builder import build_report_json


def test_report_json_is_deterministic() -> None:
    payload = {"job_id": "one", "counts": {"PASS": 1, "REVIEW": 2}}
    assert build_report_json(payload) == build_report_json(payload)
    assert build_report_json(payload).endswith(b"\n")
