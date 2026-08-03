from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

MIN_FREE_DISK_BYTES = 80 * 1024**3


class StopConditionError(RuntimeError):
    """Raised for a formal-run condition that must stop the remaining queue."""


def assert_sufficient_disk(path: Path, *, free_bytes: int | None = None) -> int:
    """Require the approved 80 GiB free-space floor and return observed bytes."""

    observed = shutil.disk_usage(path).free if free_bytes is None else free_bytes
    if observed < MIN_FREE_DISK_BYTES:
        raise StopConditionError(
            f"free disk is below the required 80 GiB floor: {observed} bytes at {path}"
        )
    return observed


def probe_gpu_health() -> dict[str, float | None]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except OSError:
        completed = None
    if completed is None or completed.returncode != 0 or not completed.stdout.strip():
        return {
            "gpu_utilization_percent": None,
            "gpu_memory_used_mib": None,
            "gpu_temperature_c": None,
        }
    fields = [field.strip() for field in completed.stdout.splitlines()[0].split(",")]
    if len(fields) != 3:
        raise StopConditionError("nvidia-smi returned an invalid GPU health row")
    try:
        utilization, memory, temperature = (float(field) for field in fields)
    except ValueError as error:
        raise StopConditionError("nvidia-smi returned non-numeric GPU health values") from error
    return {
        "gpu_utilization_percent": utilization,
        "gpu_memory_used_mib": memory,
        "gpu_temperature_c": temperature,
    }


class HeartbeatLog:
    """Append durable health and progress snapshots without rewriting history."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float] = time.time,
        disk_probe: Callable[[Path], int] | None = None,
        gpu_probe: Callable[[], Mapping[str, float | None]] = probe_gpu_health,
    ) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.clock = clock
        self.disk_probe = disk_probe or (lambda target: shutil.disk_usage(target).free)
        self.gpu_probe = gpu_probe

    def emit(
        self,
        *,
        event: str,
        run_identity: str,
        attempt: int,
        progress_current: int | None = None,
        progress_total: int | None = None,
        current_checkpoint: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        free_disk_bytes = self.disk_probe(self.path.parent)
        assert_sufficient_disk(self.path.parent, free_bytes=free_disk_bytes)
        payload: dict[str, Any] = {
            "attempt": attempt,
            "event": event,
            "free_disk_bytes": free_disk_bytes,
            "run_identity": run_identity,
            "timestamp": self.clock(),
            **self.gpu_probe(),
        }
        if progress_current is not None:
            payload["progress_current"] = progress_current
        if progress_total is not None:
            payload["progress_total"] = progress_total
        if current_checkpoint is not None:
            payload["current_checkpoint"] = current_checkpoint
        if details:
            payload["details"] = dict(details)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
