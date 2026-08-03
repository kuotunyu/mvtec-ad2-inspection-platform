from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Self, cast

from pydantic import Field

from inspection_platform.contracts._base import ContractModel


class LeaseUnavailableError(RuntimeError):
    """Raised when the project GPU lease or compute preflight is unavailable."""


class LeaseRecord(ContractModel):
    lease_id: str
    owner: str
    pid: Annotated[int, Field(gt=0)]
    process_started_at: float
    repository_identity: str
    acquired_at: float
    heartbeat_at: float


@dataclass(frozen=True, slots=True)
class ComputeProcess:
    pid: int
    process_name: str
    used_memory: str


def find_conflicting_compute_processes(
    diagnostic: str, *, own_pid: int
) -> tuple[ComputeProcess, ...]:
    """Extract only known Python, WSL, or CUDA compute processes from WDDM output."""

    conflicts: list[ComputeProcess] = []
    for line in diagnostic.splitlines():
        fields = [field.strip() for field in line.split(",", maxsplit=2)]
        if len(fields) < 2:
            continue
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        if pid == own_pid:
            continue
        process_name = fields[1]
        basename = process_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()
        known_compute = (
            basename.startswith("python")
            or basename in {"wsl", "wsl.exe", "wslhost.exe", "vmmemwsl", "torchrun"}
            or "cuda" in basename
        )
        if known_compute:
            conflicts.append(
                ComputeProcess(
                    pid=pid,
                    process_name=process_name,
                    used_memory=fields[2] if len(fields) == 3 else "unknown",
                )
            )
    return tuple(conflicts)


def _default_process_matches(pid: int, process_started_at: float) -> bool:
    try:
        import psutil  # type: ignore[import-untyped]

        process = psutil.Process(pid)
        return bool(process.is_running() and abs(process.create_time() - process_started_at) < 1.0)
    except (ImportError, OSError):
        return False
    except Exception as error:
        if error.__class__.__name__ in {"NoSuchProcess", "ZombieProcess"}:
            return False
        if error.__class__.__name__ == "AccessDenied":
            return True
        raise


def _current_process_started_at(pid: int) -> float:
    try:
        import psutil

        return float(psutil.Process(pid).create_time())
    except ImportError as error:
        raise RuntimeError("psutil is required for process-identity-safe GPU leases") from error


def _default_compute_probe() -> str:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except OSError as error:
        raise LeaseUnavailableError(f"nvidia-smi preflight is unavailable: {error}") from error
    diagnostic = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise LeaseUnavailableError(
            f"nvidia-smi compute-process preflight failed ({completed.returncode}): {diagnostic}"
        )
    return diagnostic


class LeaseHandle:
    def __init__(self, lease: GpuLease, record: LeaseRecord) -> None:
        self._lease = lease
        self.record = record
        self._released = False

    def heartbeat(self) -> None:
        if self._released:
            raise LeaseUnavailableError("cannot heartbeat a released GPU lease")
        self.record = self._lease._heartbeat(self.record)

    def release(self) -> None:
        if not self._released:
            self._lease._release(self.record)
            self._released = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class GpuLease:
    """Atomic exclusive lease that never steals from a matching live process."""

    def __init__(
        self,
        path: Path,
        *,
        repository_identity: str,
        ttl_seconds: float = 120.0,
        clock: Callable[[], float] = time.time,
        pid: int | None = None,
        process_started_at: float | None = None,
        process_matches: Callable[[int, float], bool] = _default_process_matches,
        compute_probe: Callable[[], str] = _default_compute_probe,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("GPU lease ttl_seconds must be positive")
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.repository_identity = repository_identity
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.pid = os.getpid() if pid is None else pid
        self.process_started_at = (
            _current_process_started_at(self.pid)
            if process_started_at is None
            else process_started_at
        )
        self.process_matches = process_matches
        self.compute_probe = compute_probe

    @staticmethod
    def _payload(record: LeaseRecord) -> dict[str, Any]:
        return record.model_dump(mode="json", exclude_computed_fields=True)

    def _create(self, record: LeaseRecord) -> None:
        with self.path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(self._payload(record), stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _load(self) -> LeaseRecord:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return LeaseRecord.model_validate(cast(dict[str, Any], payload))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise LeaseUnavailableError(
                f"GPU lease exists but its owner evidence is unreadable: {self.path}"
            ) from error

    def acquire(self, owner: str) -> LeaseHandle:
        if not owner.strip():
            raise ValueError("GPU lease owner must not be blank")
        now = self.clock()
        record = LeaseRecord(
            lease_id=uuid.uuid4().hex,
            owner=owner,
            pid=self.pid,
            process_started_at=self.process_started_at,
            repository_identity=self.repository_identity,
            acquired_at=now,
            heartbeat_at=now,
        )
        for _attempt in range(3):
            try:
                self._create(record)
                break
            except FileExistsError:
                existing = self._load()
                expired = now - existing.heartbeat_at > self.ttl_seconds
                process_gone = not self.process_matches(existing.pid, existing.process_started_at)
                if not (expired and process_gone):
                    raise LeaseUnavailableError(
                        "GPU lease is held by "
                        f"{existing.owner} (pid={existing.pid}, "
                        f"repo={existing.repository_identity})"
                    ) from None
                stale = self.path.with_name(
                    f"{self.path.name}.stale-{time.time_ns()}-{existing.lease_id}"
                )
                try:
                    os.replace(self.path, stale)
                except FileNotFoundError:
                    continue
        else:
            raise LeaseUnavailableError("GPU lease acquisition lost repeated atomic races")

        handle = LeaseHandle(self, record)
        try:
            diagnostic = self.compute_probe()
            conflicts = find_conflicting_compute_processes(diagnostic, own_pid=self.pid)
            if conflicts:
                names = ", ".join(f"pid={item.pid} {item.process_name}" for item in conflicts)
                raise LeaseUnavailableError(
                    f"conflicting GPU compute workload detected: {names}\n{diagnostic}"
                )
        except BaseException:
            handle.release()
            raise
        return handle

    def _heartbeat(self, record: LeaseRecord) -> LeaseRecord:
        current = self._load()
        if current.lease_id != record.lease_id:
            raise LeaseUnavailableError("GPU lease ownership changed before heartbeat")
        updated = record.model_copy(update={"heartbeat_at": self.clock()})
        temporary = self.path.with_name(f"{self.path.name}.tmp-{record.lease_id}")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(self._payload(updated), stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return updated

    def _release(self, record: LeaseRecord) -> None:
        if not self.path.exists():
            return
        current = self._load()
        if current.lease_id != record.lease_id:
            raise LeaseUnavailableError("refusing to release a GPU lease owned by another process")
        self.path.unlink()
