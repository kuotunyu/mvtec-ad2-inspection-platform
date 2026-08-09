from __future__ import annotations

from pathlib import Path

import pytest

from inspection_platform.retention import DeletionScopeError, delete_job_artifacts
from tests.system.conftest import SystemHarness


def test_deletion_removes_only_database_referenced_batch_files(
    system_harness: SystemHarness,
) -> None:
    first = system_harness.upload("clean-control.png")
    second = system_harness.upload("dent-review.png")
    result = delete_job_artifacts(
        system_harness.settings.artifact_root,
        system_harness.worker.sessions,
        str(first["id"]),
    )
    assert result.deleted_files == 1
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
        path for path in system_harness.settings.artifact_root.rglob("*") if path.is_file()
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
