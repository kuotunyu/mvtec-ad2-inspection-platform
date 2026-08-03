from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import JsonValue

from experiments.orchestration.gpu_lock import GpuLease, LeaseHandle
from experiments.orchestration.health import (
    HeartbeatLog,
    StopConditionError,
    assert_sufficient_disk,
    probe_gpu_health,
)
from inspection_platform.contracts import RunRecord, RunSpec, sha256_file


class RunStoreError(RuntimeError):
    """Raised when durable run evidence is incomplete or incompatible."""


@dataclass(slots=True)
class SupervisorPlan:
    skipped: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SupervisorSummary:
    skipped: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)
    stop_reason: str | None = None


FailureKind = Literal[
    "oom",
    "checksum_mismatch",
    "non_finite",
    "invalid_shape",
    "corrupt_checkpoint",
    "subprocess",
]


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    exit_code: int
    artifacts: dict[str, str] = field(default_factory=dict)
    error_kind: FailureKind | None = None
    message: str | None = None
    latency_ms: float | None = None
    peak_vram_mib: float | None = None


@dataclass(frozen=True, slots=True)
class RunRequest:
    spec: RunSpec
    effective_config: dict[str, JsonValue]
    attempt: int
    run_dir: Path
    resume_checkpoint: Path | None
    heartbeat: HeartbeatLog
    lease_heartbeat: Callable[[], None] | None = None


RunState = Literal["completed", "resumable", "pending", "failed", "invalid"]
RunExecutor = Callable[[RunRequest], ExecutionResult]
CommandFactory = Callable[[RunRequest], Sequence[str]]


class SubprocessExecutor:
    """Run one isolated worker process and validate its machine-readable result."""

    def __init__(
        self,
        command_factory: CommandFactory,
        *,
        heartbeat_interval_seconds: float = 10.0,
    ) -> None:
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        self.command_factory = command_factory
        self.heartbeat_interval_seconds = heartbeat_interval_seconds

    def __call__(self, request: RunRequest) -> ExecutionResult:
        stdout_path = request.run_dir / "worker.stdout.log"
        stderr_path = request.run_dir / "worker.stderr.log"
        result_path = request.run_dir / "worker-result.json"
        result_path.unlink(missing_ok=True)
        command = tuple(self.command_factory(request))
        if not command:
            return ExecutionResult(
                exit_code=1,
                error_kind="subprocess",
                message="worker command must not be empty",
            )
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with (
            stdout_path.open("ab") as stdout,
            stderr_path.open("ab") as stderr,
            subprocess.Popen(
                command,
                cwd=request.run_dir,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            ) as process,
        ):
            while True:
                try:
                    return_code = process.wait(timeout=self.heartbeat_interval_seconds)
                    break
                except subprocess.TimeoutExpired:
                    try:
                        if request.lease_heartbeat is not None:
                            request.lease_heartbeat()
                        request.heartbeat.emit(
                            event="subprocess_running",
                            run_identity=request.spec.identity,
                            attempt=request.attempt,
                            current_checkpoint=(
                                request.resume_checkpoint.relative_to(request.run_dir).as_posix()
                                if request.resume_checkpoint is not None
                                else None
                            ),
                        )
                    except BaseException:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                        raise

        if not result_path.is_file():
            return ExecutionResult(
                exit_code=return_code,
                error_kind="subprocess",
                message=f"worker exited with code {return_code} without worker-result.json",
            )
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            result = ExecutionResult(**cast(dict[str, Any], payload))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            return ExecutionResult(
                exit_code=return_code,
                error_kind="checksum_mismatch",
                message=f"worker-result.json is unreadable: {error}",
            )
        if result.exit_code != return_code:
            return ExecutionResult(
                exit_code=return_code,
                error_kind="checksum_mismatch",
                message=(
                    "worker exit code differs from worker-result.json: "
                    f"process={return_code}, result={result.exit_code}"
                ),
            )
        artifacts = dict(result.artifacts)
        artifacts.update(
            {
                "worker-result.json": sha256_file(result_path),
                "worker.stderr.log": sha256_file(stderr_path),
                "worker.stdout.log": sha256_file(stdout_path),
            }
        )
        return ExecutionResult(
            exit_code=result.exit_code,
            artifacts=artifacts,
            error_kind=result.error_kind,
            message=result.message,
            latency_ms=result.latency_ms,
            peak_vram_mib=result.peak_vram_mib,
        )


class RunStore:
    """Content-verified filesystem store for immutable formal run identities."""

    REQUIRED_DIRECTORIES = ("checkpoints", "predictions", "metrics")

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, spec: RunSpec) -> Path:
        return self.root / spec.identity

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        if temporary.exists():
            raise RunStoreError(f"temporary evidence file already exists: {temporary}")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _spec_payload(spec: RunSpec) -> dict[str, Any]:
        payload = spec.model_dump(mode="json", exclude_computed_fields=True)
        payload["canonical_sha256"] = spec.identity
        return payload

    def initialize(self, spec: RunSpec) -> Path:
        destination = self.run_dir(spec)
        if destination.exists():
            if self.load_spec(destination) != spec:
                raise RunStoreError("existing run directory has an incompatible specification")
            return destination

        temporary = Path(tempfile.mkdtemp(prefix=f".{spec.identity}.init-", dir=self.root))
        try:
            for name in self.REQUIRED_DIRECTORIES:
                (temporary / name).mkdir()
            self._write_json(temporary / "spec.json", self._spec_payload(spec))
            self._write_json(
                temporary / "record.json",
                RunRecord(spec=spec, status="pending").model_dump(
                    mode="json", exclude_computed_fields=True
                ),
            )
            (temporary / "heartbeat.jsonl").touch(exist_ok=False)
            os.replace(temporary, destination)
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            if destination.exists() and self.load_spec(destination) == spec:
                return destination
            raise
        return destination

    def load_spec(self, run_dir: Path) -> RunSpec:
        payload = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RunStoreError("spec.json root must be an object")
        canonical = payload.pop("canonical_sha256", None)
        spec = RunSpec.model_validate(cast(dict[str, Any], payload))
        if canonical != spec.identity or run_dir.name != spec.identity:
            raise RunStoreError("run specification identity mismatch")
        return spec

    @staticmethod
    def load_record(run_dir: Path) -> RunRecord:
        payload = json.loads((run_dir / "record.json").read_text(encoding="utf-8"))
        return RunRecord.model_validate(payload)

    def write_record(self, run_dir: Path, record: RunRecord) -> None:
        self._write_json(
            run_dir / "record.json",
            record.model_dump(mode="json", exclude_computed_fields=True),
        )

    @staticmethod
    def _artifacts_valid(run_dir: Path, artifacts: Mapping[str, str]) -> bool:
        if not artifacts:
            return False
        root = run_dir.resolve(strict=True)
        for relative, expected_hash in artifacts.items():
            candidate = (root / relative).resolve(strict=False)
            try:
                candidate.relative_to(root)
            except ValueError:
                return False
            if not candidate.is_file() or sha256_file(candidate) != expected_hash:
                return False
        return True

    def inspect(self, spec: RunSpec) -> RunState:
        run_dir = self.run_dir(spec)
        if not run_dir.exists():
            return "pending"
        try:
            stored_spec = self.load_spec(run_dir)
            record = self.load_record(run_dir)
        except (OSError, ValueError, json.JSONDecodeError, RunStoreError):
            return "invalid"
        if stored_spec != spec or record.spec != spec:
            return "invalid"
        if record.status == "failed":
            return "failed"
        if record.status == "completed":
            return "completed" if self._artifacts_valid(run_dir, record.artifacts) else "invalid"
        checkpoint_keys = tuple(key for key in record.artifacts if key.startswith("checkpoints/"))
        if checkpoint_keys and self._artifacts_valid(run_dir, record.artifacts):
            return "resumable"
        return "pending"

    def resume_checkpoint(self, spec: RunSpec) -> Path | None:
        run_dir = self.run_dir(spec)
        record = self.load_record(run_dir)
        if not self._artifacts_valid(run_dir, record.artifacts):
            return None
        checkpoint_keys = sorted(key for key in record.artifacts if key.startswith("checkpoints/"))
        return run_dir / checkpoint_keys[-1] if checkpoint_keys else None

    def quarantine(self, spec: RunSpec) -> Path:
        source = self.run_dir(spec)
        if not source.exists():
            raise RunStoreError("cannot quarantine a missing run directory")
        destination = self.root / f"{spec.identity}.quarantine-{time.time_ns()}"
        os.replace(source, destination)
        return destination

    def write_checkpoint(self, spec: RunSpec, content: bytes = b"checkpoint") -> Path:
        run_dir = self.initialize(spec)
        checkpoint = run_dir / "checkpoints" / "latest.ckpt"
        checkpoint.write_bytes(content)
        record = RunRecord(
            spec=spec,
            status="running",
            artifacts={"checkpoints/latest.ckpt": sha256_file(checkpoint)},
        )
        self.write_record(run_dir, record)
        return checkpoint

    def write_completed(self, spec: RunSpec, *, valid_artifacts: bool) -> Path:
        run_dir = self.initialize(spec)
        result = run_dir / "metrics" / "result.json"
        result.write_text("{}\n", encoding="utf-8")
        digest = sha256_file(result) if valid_artifacts else "f" * 64
        self.write_record(
            run_dir,
            RunRecord(
                spec=spec,
                status="completed",
                artifacts={"metrics/result.json": digest},
            ),
        )
        return run_dir


class Supervisor:
    """Plan and execute a sequential queue without reusing incompatible evidence."""

    def __init__(
        self,
        run_store: RunStore,
        *,
        runner: RunExecutor | None = None,
        gpu_lease: GpuLease | None = None,
        disk_probe: Callable[[Path], int] | None = None,
        gpu_probe: Callable[[], Mapping[str, float | None]] = probe_gpu_health,
        code_revision: str | None = None,
        environment_lock_sha256: str | None = None,
        model_revision: Callable[[RunSpec], str] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.run_store = run_store
        self.runner = runner
        self.gpu_lease = gpu_lease
        self.disk_probe = disk_probe or (lambda path: shutil.disk_usage(path).free)
        self.gpu_probe = gpu_probe
        self.code_revision = code_revision
        self.environment_lock_sha256 = environment_lock_sha256
        self.model_revision = model_revision or (lambda spec: f"anomalib:2.5.0/{spec.model_family}")
        self.clock = clock

    def plan(self, queue: Sequence[RunSpec]) -> SupervisorPlan:
        result = SupervisorPlan()
        for spec in queue:
            state = self.run_store.inspect(spec)
            if state == "completed":
                result.skipped.append(spec.identity)
            elif state == "resumable":
                result.resumed.append(spec.identity)
            elif state == "failed":
                result.failed.append(spec.identity)
            elif state == "invalid":
                self.run_store.quarantine(spec)
                result.quarantined.append(spec.identity)
                result.pending.append(spec.identity)
            else:
                result.pending.append(spec.identity)
        return result

    @staticmethod
    def _effective_config(spec: RunSpec, attempt: int) -> dict[str, JsonValue]:
        if attempt not in {1, 2}:
            raise StopConditionError(f"unsupported run attempt number: {attempt}")
        config = dict(spec.config)
        if attempt == 2:
            fallback = config.get("oom_fallback_batch_size")
            current = config.get("batch_size")
            if (
                not isinstance(fallback, int)
                or isinstance(fallback, bool)
                or not isinstance(current, int)
                or isinstance(current, bool)
                or fallback <= 0
                or fallback >= current
            ):
                raise StopConditionError("attempt 2 has no valid oom_fallback_batch_size")
            config["batch_size"] = fallback
        return config

    @staticmethod
    def _config_sha256(config: Mapping[str, JsonValue]) -> str:
        encoded = json.dumps(
            config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _write_failed(
        self,
        spec: RunSpec,
        run_dir: Path,
        *,
        attempt: int,
        message: str,
        artifacts: Mapping[str, str] | None = None,
        effective_config: Mapping[str, JsonValue] | None = None,
        started_at: float | None = None,
        exit_code: int | None = None,
        status: Literal["failed", "stopped"] = "failed",
    ) -> None:
        self.run_store.write_record(
            run_dir,
            RunRecord(
                spec=spec,
                status=status,
                attempt=attempt,
                artifacts=dict(artifacts or {}),
                error=message,
                code_revision=self.code_revision,
                config_sha256=(
                    self._config_sha256(effective_config) if effective_config is not None else None
                ),
                environment_lock_sha256=self.environment_lock_sha256,
                model_revision=self.model_revision(spec),
                started_at=started_at,
                finished_at=self.clock(),
                exit_code=exit_code,
            ),
        )

    def _run_one(
        self,
        spec: RunSpec,
        *,
        resume: bool,
        lease_handle: LeaseHandle | None,
    ) -> tuple[bool, str | None, bool]:
        assert self.runner is not None
        run_dir = self.run_store.initialize(spec)
        existing = self.run_store.load_record(run_dir)
        attempt = existing.attempt if existing.status == "running" else 1
        started_at = existing.started_at if existing.started_at is not None else self.clock()
        resume_checkpoint = self.run_store.resume_checkpoint(spec) if resume else None
        heartbeat = HeartbeatLog(
            run_dir / "heartbeat.jsonl",
            disk_probe=self.disk_probe,
            gpu_probe=self.gpu_probe,
        )

        while True:
            effective_config = self._effective_config(spec, attempt)
            assert_sufficient_disk(run_dir, free_bytes=self.disk_probe(run_dir))
            checkpoint_artifacts = {
                relative: digest
                for relative, digest in existing.artifacts.items()
                if relative.startswith("checkpoints/")
            }
            self.run_store.write_record(
                run_dir,
                RunRecord(
                    spec=spec,
                    status="running",
                    attempt=attempt,
                    artifacts=checkpoint_artifacts,
                    code_revision=self.code_revision,
                    config_sha256=self._config_sha256(effective_config),
                    environment_lock_sha256=self.environment_lock_sha256,
                    model_revision=self.model_revision(spec),
                    started_at=started_at,
                ),
            )
            heartbeat.emit(
                event="attempt_started",
                run_identity=spec.identity,
                attempt=attempt,
                current_checkpoint=(
                    resume_checkpoint.relative_to(run_dir).as_posix()
                    if resume_checkpoint is not None
                    else None
                ),
                details={
                    "effective_config_sha256": self._config_sha256(effective_config),
                    "batch_size": effective_config.get("batch_size"),
                },
            )
            if lease_handle is not None:
                lease_handle.heartbeat()
            request = RunRequest(
                spec=spec,
                effective_config=effective_config,
                attempt=attempt,
                run_dir=run_dir,
                resume_checkpoint=resume_checkpoint,
                heartbeat=heartbeat,
                lease_heartbeat=(lease_handle.heartbeat if lease_handle is not None else None),
            )
            try:
                result = self.runner(request)
            except StopConditionError:
                raise
            except Exception as error:
                result = ExecutionResult(
                    exit_code=1,
                    error_kind="subprocess",
                    message=f"runner exception: {error.__class__.__name__}: {error}",
                )
            if lease_handle is not None:
                lease_handle.heartbeat()

            if result.exit_code == 0 and result.error_kind is None:
                if not self.run_store._artifacts_valid(run_dir, result.artifacts):
                    message = "checksum mismatch or missing output artifact"
                    self._write_failed(
                        spec,
                        run_dir,
                        attempt=attempt,
                        message=message,
                        artifacts=result.artifacts,
                        effective_config=effective_config,
                        started_at=started_at,
                        exit_code=result.exit_code,
                    )
                    heartbeat.emit(
                        event="stop_condition",
                        run_identity=spec.identity,
                        attempt=attempt,
                        details={"reason": message},
                    )
                    self.run_store.quarantine(spec)
                    return False, message, True
                self.run_store.write_record(
                    run_dir,
                    RunRecord(
                        spec=spec,
                        status="completed",
                        attempt=attempt,
                        artifacts=result.artifacts,
                        code_revision=self.code_revision,
                        config_sha256=self._config_sha256(effective_config),
                        environment_lock_sha256=self.environment_lock_sha256,
                        model_revision=self.model_revision(spec),
                        started_at=started_at,
                        finished_at=self.clock(),
                        latency_ms=result.latency_ms,
                        peak_vram_mib=result.peak_vram_mib,
                        exit_code=result.exit_code,
                    ),
                )
                heartbeat.emit(
                    event="attempt_completed",
                    run_identity=spec.identity,
                    attempt=attempt,
                    details={
                        "latency_ms": result.latency_ms,
                        "peak_vram_mib": result.peak_vram_mib,
                    },
                )
                return True, None, False

            if result.error_kind == "oom" and attempt == 1:
                fallback = effective_config.get("oom_fallback_batch_size")
                current = effective_config.get("batch_size")
                valid_fallback = (
                    isinstance(fallback, int)
                    and not isinstance(fallback, bool)
                    and isinstance(current, int)
                    and not isinstance(current, bool)
                    and 0 < fallback < current
                )
                if valid_fallback:
                    heartbeat.emit(
                        event="oom_retry",
                        run_identity=spec.identity,
                        attempt=attempt,
                        details={
                            "failed_batch_size": current,
                            "fallback_batch_size": fallback,
                        },
                    )
                    attempt = 2
                    existing = RunRecord(
                        spec=spec,
                        status="running",
                        attempt=attempt,
                        artifacts=checkpoint_artifacts,
                    )
                    continue

            message = result.message or f"runner exited with code {result.exit_code}"
            if result.error_kind == "oom" and attempt == 2:
                message = f"second OOM: {message}"
            self._write_failed(
                spec,
                run_dir,
                attempt=attempt,
                message=message,
                artifacts=result.artifacts,
                effective_config=effective_config,
                started_at=started_at,
                exit_code=result.exit_code,
                status="stopped" if result.error_kind == "subprocess" else "failed",
            )
            heartbeat.emit(
                event="attempt_failed",
                run_identity=spec.identity,
                attempt=attempt,
                details={"kind": result.error_kind, "reason": message},
            )
            quarantine = result.error_kind in {
                "checksum_mismatch",
                "non_finite",
                "invalid_shape",
                "corrupt_checkpoint",
            }
            if quarantine:
                self.run_store.quarantine(spec)
            return False, message, quarantine

    def run(self, queue: Sequence[RunSpec]) -> SupervisorSummary:
        if self.runner is None:
            raise RuntimeError("Supervisor.run requires an injected run executor")
        specs = tuple(queue)
        plan = self.plan(specs)
        summary = SupervisorSummary(
            skipped=list(plan.skipped),
            resumed=list(plan.resumed),
            failed=list(plan.failed),
            quarantined=list(plan.quarantined),
        )
        if plan.failed:
            first_failed_index = next(
                index for index, spec in enumerate(specs) if spec.identity in plan.failed
            )
            failed_spec = specs[first_failed_index]
            failed_record = self.run_store.load_record(self.run_store.run_dir(failed_spec))
            summary.stop_reason = failed_record.error
            summary.stopped.extend(
                spec.identity
                for spec in specs[first_failed_index + 1 :]
                if spec.identity not in plan.skipped
            )
            return summary
        if len(plan.skipped) == len(specs):
            return summary
        lease_handle = (
            self.gpu_lease.acquire("formal-experiment-queue")
            if self.gpu_lease is not None
            else None
        )
        try:
            for index, spec in enumerate(specs):
                if spec.identity in plan.skipped:
                    continue
                try:
                    completed, reason, quarantined = self._run_one(
                        spec,
                        resume=spec.identity in plan.resumed,
                        lease_handle=lease_handle,
                    )
                except StopConditionError as error:
                    run_dir = self.run_store.initialize(spec)
                    record = self.run_store.load_record(run_dir)
                    self._write_failed(
                        spec,
                        run_dir,
                        attempt=record.attempt,
                        message=str(error),
                        artifacts=record.artifacts,
                        effective_config=spec.config,
                        started_at=record.started_at,
                    )
                    completed, reason, quarantined = False, str(error), False
                if completed:
                    summary.completed.append(spec.identity)
                    continue
                summary.failed.append(spec.identity)
                if quarantined:
                    summary.quarantined.append(spec.identity)
                summary.stop_reason = reason
                summary.stopped.extend(
                    item.identity
                    for item in specs[index + 1 :]
                    if item.identity not in plan.skipped
                )
                break
        finally:
            if lease_handle is not None:
                lease_handle.release()
        return summary
