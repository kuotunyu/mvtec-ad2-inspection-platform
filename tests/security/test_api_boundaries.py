from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import SpooledTemporaryFile as RealSpooledTemporaryFile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient, Response
from pytest import MonkeyPatch
from starlette.datastructures import UploadFile

from apps.api.main import create_app
from inspection_platform.settings import Settings
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


def test_backend_rejects_excess_file_count_before_reading_uploads(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        max_archive_files=2,
    )
    client = TestClient(create_app(settings))
    response = client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", (f"{index}.png", b"x", "image/png")) for index in range(3)],
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_many_files"
    assert client.get("/api/v1/jobs").json()["total"] == 0


def test_upload_read_is_bounded_to_configured_limit(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        max_upload_bytes=16,
    )
    observed_sizes: list[int] = []
    original_read = UploadFile.read

    async def bounded_read(self: UploadFile, size: int = -1) -> bytes:
        observed_sizes.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", bounded_read)
    response = TestClient(create_app(settings)).post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", ("oversize.png", b"x" * 17, "image/png"))],
    )
    assert response.status_code == 201
    assert observed_sizes == [17]


def test_total_multipart_body_is_rejected_before_endpoint_parsing(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        max_archive_uncompressed_bytes=64,
    )
    client = TestClient(create_app(settings))
    response = client.post(
        "/api/v1/jobs",
        data={"category": "can"},
        files=[("files", ("part.png", b"x" * 128, "image/png"))],
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"
    assert client.get("/api/v1/jobs").json()["total"] == 0


def test_chunked_multipart_body_is_bounded_while_streaming(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        max_archive_uncompressed_bytes=128,
    )
    boundary = "inspection-boundary"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="category"\r\n\r\n'
            f'can\r\n--{boundary}\r\nContent-Disposition: form-data; name="files"; '
            f'filename="part.png"\r\nContent-Type: image/png\r\n\r\n'
        ).encode()
        + b"x" * 256
        + f"\r\n--{boundary}--\r\n".encode()
    )
    chunks = (body[index : index + 31] for index in range(0, len(body), 31))

    response = TestClient(create_app(settings)).post(
        "/api/v1/jobs",
        content=chunks,
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"


def test_concurrent_async_uploads_do_not_treat_tasks_as_lock_reentry(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
    )
    app = create_app(settings)
    image = Path("fixtures/public-demo/images/clean-control.png").read_bytes()
    original_read = UploadFile.read
    first_read = asyncio.Event()
    second_read = asyncio.Event()
    release_first = asyncio.Event()
    release_second = asyncio.Event()
    read_count = 0

    async def coordinated_read(self: UploadFile, size: int = -1) -> bytes:
        nonlocal read_count
        read_count += 1
        if read_count == 1:
            first_read.set()
            await release_first.wait()
        elif read_count == 2:
            second_read.set()
            await release_second.wait()
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", coordinated_read)

    async def scenario() -> tuple[Response, Response]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://inspection.test"
        ) as client:

            async def upload(name: str) -> Response:
                return await client.post(
                    "/api/v1/jobs",
                    data={"category": "can"},
                    files={"files": (name, image, "image/png")},
                )

            first = asyncio.create_task(upload("first.png"))
            await asyncio.wait_for(first_read.wait(), 5)
            second = asyncio.create_task(upload("second.png"))
            await asyncio.wait_for(second_read.wait(), 5)
            release_first.set()
            try:
                first_response = await asyncio.wait_for(first, 5)
            finally:
                release_second.set()
            second_response = await asyncio.wait_for(second, 5)
            return first_response, second_response

    responses = asyncio.run(scenario())

    assert [response.status_code for response in responses] == [201, 201]
    assert TestClient(app).get("/api/v1/jobs").json()["total"] == 2


def test_valid_upload_staging_uses_configured_spool_root(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    spool_root = tmp_path / "spool"
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        spool_root=spool_root,
    )
    observed_roots: list[Path] = []

    def observed_spool(*args, **kwargs):
        observed_roots.append(Path(kwargs["dir"]).resolve())
        return RealSpooledTemporaryFile(*args, **kwargs)

    monkeypatch.setattr("apps.api.main.SpooledTemporaryFile", observed_spool)
    image = Path("fixtures/public-demo/images/clean-control.png").read_bytes()

    response = TestClient(create_app(settings)).post(
        "/api/v1/jobs",
        data={"category": "can"},
        files={"files": ("control.png", image, "image/png")},
    )

    assert response.status_code == 201
    assert observed_roots == [spool_root.resolve()]


def test_api_fails_fast_when_spool_cannot_hold_parser_and_staging_copies(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        spool_root=tmp_path / "spool",
        max_archive_uncompressed_bytes=100,
        max_upload_bytes=25,
    )
    monkeypatch.setattr(
        "apps.api.main.disk_usage",
        lambda _path: SimpleNamespace(total=1_000, used=776, free=224),
    )

    with pytest.raises(RuntimeError, match="spool capacity"):
        create_app(settings)
