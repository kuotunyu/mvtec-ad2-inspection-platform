from __future__ import annotations

import pytest

from experiments.orchestration.health import StopConditionError
from experiments.orchestration.resource_guard import (
    ResourceGuard,
    ResourceLimits,
    ResourceSnapshot,
    assert_resource_preflight,
)


def _snapshot(
    *,
    ram: float = 20_000.0,
    gpu: float = 500.0,
    temperature: float = 45.0,
) -> ResourceSnapshot:
    return ResourceSnapshot(
        system_available_mib=ram,
        gpu_memory_used_mib=gpu,
        gpu_temperature_c=temperature,
    )


def _limits(*, timeout: float = 2_700.0) -> ResourceLimits:
    return ResourceLimits(timeout_seconds=timeout)


def test_preflight_requires_memory_disk_and_gpu_headroom() -> None:
    assert_resource_preflight(_snapshot(), free_disk_bytes=200 * 1024**3)

    with pytest.raises(StopConditionError, match="16 GiB"):
        assert_resource_preflight(_snapshot(ram=15_000), free_disk_bytes=200 * 1024**3)
    with pytest.raises(StopConditionError, match="160 GiB"):
        assert_resource_preflight(_snapshot(), free_disk_bytes=150 * 1024**3)
    with pytest.raises(StopConditionError, match="GPU memory"):
        assert_resource_preflight(_snapshot(gpu=22_600), free_disk_bytes=200 * 1024**3)
    with pytest.raises(StopConditionError, match="temperature"):
        assert_resource_preflight(_snapshot(temperature=83), free_disk_bytes=200 * 1024**3)


def test_guard_stops_only_after_three_consecutive_breaches() -> None:
    snapshots = iter((_snapshot(ram=3_000), _snapshot(ram=3_000), _snapshot(ram=3_000)))
    guard = ResourceGuard(probe=lambda: next(snapshots), limits=_limits())

    assert guard(10.0) is None
    assert guard(20.0) is None
    assert guard(30.0) == "system available memory below 4096 MiB for 3 samples"


def test_healthy_sample_resets_debounce() -> None:
    snapshots = iter(
        (
            _snapshot(ram=3_000),
            _snapshot(ram=20_000),
            _snapshot(ram=3_000),
            _snapshot(ram=3_000),
            _snapshot(ram=3_000),
        )
    )
    guard = ResourceGuard(probe=lambda: next(snapshots), limits=_limits())

    assert [guard(value) for value in (10.0, 20.0, 30.0, 40.0, 50.0)] == [
        None,
        None,
        None,
        None,
        "system available memory below 4096 MiB for 3 samples",
    ]


def test_guard_covers_gpu_memory_temperature_and_timeout() -> None:
    gpu_guard = ResourceGuard(probe=lambda: _snapshot(gpu=22_501), limits=_limits())
    assert gpu_guard(10.0) is None
    assert gpu_guard(20.0) is None
    assert gpu_guard(30.0) == "GPU memory above 22500 MiB for 3 samples"

    temperature_guard = ResourceGuard(probe=lambda: _snapshot(temperature=83), limits=_limits())
    assert temperature_guard(10.0) is None
    assert temperature_guard(20.0) is None
    assert temperature_guard(30.0) == "GPU temperature at or above 83 C for 3 samples"

    timeout_guard = ResourceGuard(probe=lambda: _snapshot(), limits=_limits(timeout=60.0))
    assert timeout_guard(59.9) is None
    assert timeout_guard(60.0) == "wall-clock limit reached at 60 seconds"
