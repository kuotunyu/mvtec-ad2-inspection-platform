from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Event, Thread

import pytest
from sqlalchemy import select

from inspection_platform.db.models import AuditEvent, InspectionImage, Job
from inspection_platform.retention import (
    DeletionScopeError,
    delete_job_artifacts,
    purge_expired_jobs,
    purge_orphan_artifacts,
)
from tests.system.conftest import SystemHarness


def test_deletion_removes_only_database_referenced_batch_files(
    system_harness: SystemHarness,
) -> None:
    first = system_harness.upload("clean-control.png")
    second = system_harness.upload("dent-review.png")
    assert system_harness.worker.process_once()
    detail = system_harness.client.get(f"/api/v1/jobs/{first['id']}").json()
    evidence_urls = (
        detail["images"][0]["source_url"],
        detail["images"][0]["anomaly_map_url"],
        detail["images"][0]["overlay_url"],
    )
    result = delete_job_artifacts(
        system_harness.settings.artifact_root,
        system_harness.worker.sessions,
        str(first["id"]),
    )
    assert result.deleted_files == 3
    assert all(system_harness.client.get(url).status_code == 404 for url in evidence_urls)
    assert system_harness.client.get(f"/api/v1/jobs/{second['id']}").status_code == 200
    repeated = delete_job_artifacts(
        system_harness.settings.artifact_root,
        system_harness.worker.sessions,
        str(first["id"]),
    )
    assert repeated.deleted_files == 0


def test_deletion_rejects_symlink_substitution(
    system_harness: SystemHarness, tmp_path: Path
) -> None:
    created = system_harness.upload("clean-control.png")
    artifact = next(
        path
        for path in system_harness.settings.artifact_root.rglob("*")
        if path.is_file() and len(path.name) == 64
    )
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"keep")
    artifact.unlink()
    try:
        artifact.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(DeletionScopeError):
        delete_job_artifacts(
            system_harness.settings.artifact_root,
            system_harness.worker.sessions,
            str(created["id"]),
        )
    assert outside.read_bytes() == b"keep"


def test_retention_purges_only_terminal_jobs_older_than_cutoff(
    system_harness: SystemHarness,
) -> None:
    expired = system_harness.upload("clean-control.png")
    current = system_harness.upload("dent-review.png")
    assert system_harness.worker.process_once()
    assert system_harness.worker.process_once()
    with system_harness.worker.sessions() as session, session.begin():
        old_job = session.get(Job, expired["id"])
        assert old_job is not None
        old_job.created_at = datetime.now(UTC) - timedelta(days=8)

    result = purge_expired_jobs(
        system_harness.settings.artifact_root,
        system_harness.worker.sessions,
        datetime.now(UTC) - timedelta(days=7),
    )

    assert result.deleted_jobs == 1
    assert result.deleted_files == 3
    expired_detail = system_harness.client.get(f"/api/v1/jobs/{expired['id']}").json()
    current_detail = system_harness.client.get(f"/api/v1/jobs/{current['id']}").json()
    assert system_harness.client.get(expired_detail["images"][0]["source_url"]).status_code == 404
    assert system_harness.client.get(current_detail["images"][0]["source_url"]).status_code == 200


def test_explicit_deletion_rejects_active_job_without_tombstone(
    system_harness: SystemHarness,
) -> None:
    created = system_harness.upload("clean-control.png")
    response = system_harness.client.delete(f"/api/v1/jobs/{created['id']}/artifacts")

    assert response.status_code == 409
    assert response.json()["code"] == "job_not_terminal"
    with system_harness.worker.sessions() as session:
        tombstone = session.scalar(
            select(AuditEvent).where(
                AuditEvent.resource_id == created["id"],
                AuditEvent.action == "job.artifacts_deleted",
            )
        )
    assert tombstone is None


def test_tombstone_revokes_shared_artifact_routes_without_deleting_shared_blobs(
    system_harness: SystemHarness,
) -> None:
    first = system_harness.upload("clean-control.png")
    second = system_harness.upload("clean-control.png")
    assert system_harness.worker.process_once()
    assert system_harness.worker.process_once()
    first_detail = system_harness.client.get(f"/api/v1/jobs/{first['id']}").json()
    second_detail = system_harness.client.get(f"/api/v1/jobs/{second['id']}").json()
    first_urls = tuple(
        first_detail["images"][0][key] for key in ("source_url", "anomaly_map_url", "overlay_url")
    )
    second_urls = tuple(
        second_detail["images"][0][key] for key in ("source_url", "anomaly_map_url", "overlay_url")
    )

    response = system_harness.client.delete(f"/api/v1/jobs/{first['id']}/artifacts")

    assert response.status_code == 200
    assert response.json()["deleted_files"] == 0
    assert all(system_harness.client.get(url).status_code == 404 for url in first_urls)
    assert all(system_harness.client.get(url).status_code == 200 for url in second_urls)


def test_orphan_collector_removes_only_old_unreferenced_files(
    system_harness: SystemHarness,
) -> None:
    created = system_harness.upload("clean-control.png")
    detail = system_harness.client.get(f"/api/v1/jobs/{created['id']}").json()
    referenced_url = detail["images"][0]["source_url"]
    old_orphan = system_harness.settings.artifact_root / "ff" / ("f" * 64)
    recent_orphan = system_harness.settings.artifact_root / "ee" / ("e" * 64)
    old_orphan.parent.mkdir(parents=True)
    recent_orphan.parent.mkdir(parents=True)
    old_orphan.write_bytes(b"old orphan")
    recent_orphan.write_bytes(b"recent orphan")
    old_timestamp = (datetime.now(UTC) - timedelta(days=8)).timestamp()
    old_orphan.touch()
    os.utime(old_orphan, (old_timestamp, old_timestamp))

    deleted = purge_orphan_artifacts(
        system_harness.settings.artifact_root,
        system_harness.worker.sessions,
        datetime.now(UTC) - timedelta(days=7),
    )

    assert deleted == 1
    assert not old_orphan.exists()
    assert recent_orphan.exists()
    assert system_harness.client.get(referenced_url).status_code == 200


def test_orphan_collection_cannot_delete_a_concurrently_reused_blob(
    system_harness: SystemHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = Path("fixtures/public-demo/images/clean-control.png").read_bytes()
    artifact_key = sha256(content).hexdigest()
    aged_orphan = system_harness.settings.artifact_root / artifact_key[:2] / artifact_key
    aged_orphan.parent.mkdir(parents=True)
    aged_orphan.write_bytes(content)
    old_timestamp = (datetime.now(UTC) - timedelta(days=8)).timestamp()
    os.utime(aged_orphan, (old_timestamp, old_timestamp))
    unlink_started = Event()
    allow_unlink = Event()
    original_unlink = Path.unlink

    def controlled_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == aged_orphan:
            unlink_started.set()
            assert allow_unlink.wait(5)
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", controlled_unlink)
    collector_errors: list[BaseException] = []
    upload_result: list[dict[str, object]] = []

    def collect() -> None:
        try:
            purge_orphan_artifacts(
                system_harness.settings.artifact_root,
                system_harness.worker.sessions,
                datetime.now(UTC) - timedelta(days=7),
            )
        except BaseException as exc:
            collector_errors.append(exc)

    collector = Thread(target=collect)
    collector.start()
    assert unlink_started.wait(5)
    uploader = Thread(
        target=lambda: upload_result.append(system_harness.upload("clean-control.png"))
    )
    uploader.start()
    uploader.join(timeout=1)
    allow_unlink.set()
    collector.join(timeout=5)
    uploader.join(timeout=5)

    assert not collector_errors
    assert len(upload_result) == 1
    detail = system_harness.client.get(f"/api/v1/jobs/{upload_result[0]['id']}").json()
    assert aged_orphan.is_file()
    assert system_harness.client.get(detail["images"][0]["source_url"]).status_code == 200


def test_job_deletion_cannot_delete_a_concurrently_published_shared_blob(
    system_harness: SystemHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = system_harness.upload("clean-control.png")
    assert system_harness.worker.process_once()
    original_detail = system_harness.client.get(f"/api/v1/jobs/{original['id']}").json()
    source_url = original_detail["images"][0]["source_url"]
    source_key = source_url.removesuffix("/source").rsplit("/", 1)[-1]
    with system_harness.worker.sessions() as session:
        image = session.get(InspectionImage, source_key)
        assert image is not None
        source_path = (
            system_harness.settings.artifact_root / image.artifact_key[:2] / image.artifact_key
        )
    unlink_started = Event()
    allow_unlink = Event()
    original_unlink = Path.unlink

    def controlled_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == source_path:
            unlink_started.set()
            assert allow_unlink.wait(5)
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", controlled_unlink)
    deletion_errors: list[BaseException] = []
    upload_result: list[dict[str, object]] = []

    def delete() -> None:
        try:
            delete_job_artifacts(
                system_harness.settings.artifact_root,
                system_harness.worker.sessions,
                str(original["id"]),
            )
        except BaseException as exc:
            deletion_errors.append(exc)

    deleter = Thread(target=delete)
    deleter.start()
    assert unlink_started.wait(5)
    uploader = Thread(
        target=lambda: upload_result.append(system_harness.upload("clean-control.png"))
    )
    uploader.start()
    uploader.join(timeout=1)
    allow_unlink.set()
    deleter.join(timeout=5)
    uploader.join(timeout=5)

    assert not deletion_errors
    assert len(upload_result) == 1
    detail = system_harness.client.get(f"/api/v1/jobs/{upload_result[0]['id']}").json()
    assert source_path.is_file()
    assert system_harness.client.get(detail["images"][0]["source_url"]).status_code == 200
