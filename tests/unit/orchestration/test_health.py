from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.orchestration.health import (
    MIN_FREE_DISK_BYTES,
    HeartbeatLog,
    StopConditionError,
    assert_sufficient_disk,
)


def test_disk_below_80_gib_is_a_stop_condition(tmp_path: Path) -> None:
    with pytest.raises(StopConditionError, match="80 GiB"):
        assert_sufficient_disk(tmp_path, free_bytes=MIN_FREE_DISK_BYTES - 1)

    assert_sufficient_disk(tmp_path, free_bytes=MIN_FREE_DISK_BYTES)


def test_heartbeat_is_append_only_jsonl_with_required_health_fields(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.jsonl"
    heartbeat = HeartbeatLog(
        path,
        clock=lambda: 123.5,
        disk_probe=lambda _path: 100 * 1024**3,
        gpu_probe=lambda: {
            "gpu_utilization_percent": 88.0,
            "gpu_memory_used_mib": 4096.0,
            "gpu_temperature_c": 61.0,
        },
    )

    heartbeat.emit(
        event="attempt_running",
        run_identity="a" * 64,
        attempt=2,
        progress_current=3,
        progress_total=10,
        current_checkpoint="checkpoints/latest.ckpt",
    )
    heartbeat.emit(event="attempt_completed", run_identity="a" * 64, attempt=2)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["attempt_running", "attempt_completed"]
    assert rows[0] == {
        "attempt": 2,
        "current_checkpoint": "checkpoints/latest.ckpt",
        "event": "attempt_running",
        "free_disk_bytes": 100 * 1024**3,
        "gpu_memory_used_mib": 4096.0,
        "gpu_temperature_c": 61.0,
        "gpu_utilization_percent": 88.0,
        "progress_current": 3,
        "progress_total": 10,
        "run_identity": "a" * 64,
        "timestamp": 123.5,
    }
