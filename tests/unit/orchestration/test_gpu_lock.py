from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.orchestration.gpu_lock import (
    GpuLease,
    LeaseUnavailableError,
    find_conflicting_compute_processes,
)


def test_gpu_lease_is_exclusive_and_owner_can_heartbeat(tmp_path: Path) -> None:
    now = [100.0]
    path = tmp_path / "gpu.lock"
    lease = GpuLease(
        path,
        repository_identity="repo-a",
        ttl_seconds=30,
        clock=lambda: now[0],
        pid=101,
        process_started_at=10.0,
        process_matches=lambda _pid, _started: True,
        compute_probe=lambda: "",
    )

    handle = lease.acquire("formal-queue")
    first = json.loads(path.read_text(encoding="utf-8"))
    now[0] = 115.0
    handle.heartbeat()
    second = json.loads(path.read_text(encoding="utf-8"))

    assert first["owner"] == "formal-queue"
    assert first["pid"] == 101
    assert first["process_started_at"] == 10.0
    assert first["repository_identity"] == "repo-a"
    assert second["heartbeat_at"] == 115.0
    with pytest.raises(LeaseUnavailableError, match="held"):
        lease.acquire("competitor")
    handle.release()
    assert not path.exists()


def test_expired_lease_is_reclaimed_only_when_process_identity_is_gone(tmp_path: Path) -> None:
    path = tmp_path / "gpu.lock"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "lease_id": "old",
                "owner": "old-owner",
                "pid": 9,
                "process_started_at": 5.0,
                "repository_identity": "repo-old",
                "acquired_at": 10.0,
                "heartbeat_at": 20.0,
            }
        ),
        encoding="utf-8",
    )
    lease = GpuLease(
        path,
        repository_identity="repo-new",
        ttl_seconds=30,
        clock=lambda: 100.0,
        pid=101,
        process_started_at=90.0,
        process_matches=lambda _pid, _started: False,
        compute_probe=lambda: "",
    )

    handle = lease.acquire("new-owner")

    assert json.loads(path.read_text(encoding="utf-8"))["owner"] == "new-owner"
    assert len(tuple(tmp_path.glob("gpu.lock.stale-*"))) == 1
    handle.release()


def test_expired_lease_with_matching_live_process_is_not_reclaimed(tmp_path: Path) -> None:
    path = tmp_path / "gpu.lock"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "lease_id": "old",
                "owner": "old-owner",
                "pid": 9,
                "process_started_at": 5.0,
                "repository_identity": "repo-old",
                "acquired_at": 10.0,
                "heartbeat_at": 20.0,
            }
        ),
        encoding="utf-8",
    )
    lease = GpuLease(
        path,
        repository_identity="repo-new",
        ttl_seconds=30,
        clock=lambda: 100.0,
        pid=101,
        process_started_at=90.0,
        process_matches=lambda _pid, _started: True,
        compute_probe=lambda: "",
    )

    with pytest.raises(LeaseUnavailableError, match="held"):
        lease.acquire("new-owner")
    assert json.loads(path.read_text(encoding="utf-8"))["owner"] == "old-owner"


def test_compute_preflight_ignores_desktop_entries_but_detects_python_and_wsl() -> None:
    output = "\n".join(
        (
            "101, C:\\Windows\\explorer.exe, N/A",
            "202, C:\\Python312\\python.exe, 2048 MiB",
            "303, C:\\Windows\\System32\\wsl.exe, 1024 MiB",
            "404, C:\\Program Files\\OpenAI\\ChatGPT.exe, N/A",
        )
    )

    conflicts = find_conflicting_compute_processes(output, own_pid=999)

    assert [(item.pid, item.process_name) for item in conflicts] == [
        (202, "C:\\Python312\\python.exe"),
        (303, "C:\\Windows\\System32\\wsl.exe"),
    ]


def test_conflicting_compute_workload_releases_new_lease_and_preserves_diagnostic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "gpu.lock"
    output = "202, C:\\Python312\\python.exe, 2048 MiB"
    lease = GpuLease(
        path,
        repository_identity="repo-a",
        ttl_seconds=30,
        clock=lambda: 100.0,
        pid=101,
        process_started_at=90.0,
        process_matches=lambda _pid, _started: True,
        compute_probe=lambda: output,
    )

    with pytest.raises(LeaseUnavailableError, match=r"python\.exe") as error:
        lease.acquire("formal-queue")

    assert output in str(error.value)
    assert not path.exists()
