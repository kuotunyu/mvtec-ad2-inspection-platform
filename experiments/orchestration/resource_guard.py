from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from experiments.orchestration.health import StopConditionError, probe_gpu_health

MIB = 1024**2
GIB = 1024**3


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    system_available_mib: float
    gpu_memory_used_mib: float
    gpu_temperature_c: float


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    timeout_seconds: float
    preflight_system_available_mib: float = 16 * 1024
    preflight_free_disk_bytes: int = 160 * GIB
    runtime_system_available_mib: float = 4 * 1024
    runtime_gpu_memory_mib: float = 22_500
    runtime_gpu_temperature_c: float = 83
    consecutive_breaches: int = 3

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("resource timeout must be positive")
        if self.consecutive_breaches <= 0:
            raise ValueError("consecutive breach count must be positive")


def probe_resource_snapshot() -> ResourceSnapshot:
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError as error:
        raise StopConditionError("psutil is required for resource guarding") from error

    gpu = probe_gpu_health()
    memory = gpu.get("gpu_memory_used_mib")
    temperature = gpu.get("gpu_temperature_c")
    if memory is None or temperature is None:
        raise StopConditionError("GPU health is unavailable for resource guarding")
    return ResourceSnapshot(
        system_available_mib=float(psutil.virtual_memory().available / MIB),
        gpu_memory_used_mib=float(memory),
        gpu_temperature_c=float(temperature),
    )


def assert_resource_preflight(
    snapshot: ResourceSnapshot,
    *,
    free_disk_bytes: int,
    limits: ResourceLimits | None = None,
) -> None:
    checked = limits or ResourceLimits(timeout_seconds=2_700)
    if snapshot.system_available_mib < checked.preflight_system_available_mib:
        raise StopConditionError("system available memory is below the required 16 GiB")
    if free_disk_bytes < checked.preflight_free_disk_bytes:
        raise StopConditionError("free disk is below the required 160 GiB")
    if snapshot.gpu_memory_used_mib > checked.runtime_gpu_memory_mib:
        raise StopConditionError("GPU memory lacks the required resource headroom")
    if snapshot.gpu_temperature_c >= checked.runtime_gpu_temperature_c:
        raise StopConditionError("GPU temperature is at or above the 83 C start limit")


class ResourceGuard:
    def __init__(
        self,
        *,
        probe: Callable[[], ResourceSnapshot] = probe_resource_snapshot,
        limits: ResourceLimits,
    ) -> None:
        self.probe = probe
        self.limits = limits
        self._last_reason: str | None = None
        self._consecutive = 0

    def _breach_reason(self, snapshot: ResourceSnapshot) -> str | None:
        if snapshot.system_available_mib < self.limits.runtime_system_available_mib:
            return "system available memory below 4096 MiB"
        if snapshot.gpu_memory_used_mib > self.limits.runtime_gpu_memory_mib:
            return "GPU memory above 22500 MiB"
        if snapshot.gpu_temperature_c >= self.limits.runtime_gpu_temperature_c:
            return "GPU temperature at or above 83 C"
        return None

    def __call__(self, elapsed_seconds: float) -> str | None:
        if elapsed_seconds >= self.limits.timeout_seconds:
            seconds = int(self.limits.timeout_seconds)
            return f"wall-clock limit reached at {seconds} seconds"
        reason = self._breach_reason(self.probe())
        if reason is None:
            self._last_reason = None
            self._consecutive = 0
            return None
        if reason == self._last_reason:
            self._consecutive += 1
        else:
            self._last_reason = reason
            self._consecutive = 1
        if self._consecutive >= self.limits.consecutive_breaches:
            return f"{reason} for {self.limits.consecutive_breaches} samples"
        return None


__all__ = [
    "ResourceGuard",
    "ResourceLimits",
    "ResourceSnapshot",
    "assert_resource_preflight",
    "probe_resource_snapshot",
]
