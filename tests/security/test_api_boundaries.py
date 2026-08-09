from __future__ import annotations

from pathlib import Path

from tests.system.conftest import SystemHarness


def test_upload_sanitizes_unicode_path_and_bounds_oversize(
    system_harness: SystemHarness,
) -> None:
    image = Path("fixtures/public-demo/images/clean-control.png").read_bytes()
    response = system_harness.client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[
            ("files", ("../ＦＯＯ\r\n.csv.png", image, "image/png")),  # noqa: RUF001
            (
                "files",
                ("huge.png", b"x" * (system_harness.settings.max_upload_bytes + 1), "image/png"),
            ),
        ],
        headers={"x-request-id": "bad\r\nid"},
    )
    assert response.status_code == 201
    system_harness.worker.process_once()
    detail = system_harness.client.get(f"/api/v1/jobs/{response.json()['id']}").json()
    assert detail["images"][0]["filename"] == "FOO.csv.png"
    assert detail["images"][1]["error"] == "invalid_upload"
    assert "\r" not in str(detail) and "\n" not in str(detail)


def test_invalid_identifier_and_duplicate_json_keys_fail_safely(
    system_harness: SystemHarness,
) -> None:
    missing = system_harness.client.get(
        "/api/v1/jobs/<script>", headers={"authorization": "Bearer secret"}
    )
    assert missing.status_code == 404
    assert set(missing.json()) == {"code", "message", "request_id"}
    created = system_harness.upload("scratch-review.png")
    system_harness.worker.process_once()
    image_id = system_harness.client.get(f"/api/v1/jobs/{created['id']}").json()["images"][0]["id"]
    duplicate = system_harness.client.post(
        f"/api/v1/reviews/{image_id}",
        content='{"decision":"ACCEPT","decision":"REJECT","expected_revision":0}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == "duplicate_json_key"


def test_reports_neutralize_html_and_spreadsheet_formulae(
    system_harness: SystemHarness,
) -> None:
    image = Path("fixtures/public-demo/images/clean-control.png").read_bytes()
    created = system_harness.client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", ("=2+3<script>.png", image, "image/png"))],
    ).json()
    system_harness.worker.process_once()
    csv_report = system_harness.client.get(f"/api/v1/jobs/{created['id']}/report.csv")
    html_report = system_harness.client.get(f"/api/v1/jobs/{created['id']}/report.html")
    assert b"'=2+3" in csv_report.content
    assert b"<script>" not in html_report.content
