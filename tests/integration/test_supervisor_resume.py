from __future__ import annotations

from pathlib import Path

from experiments.orchestration.supervisor import (
    ExecutionResult,
    RunRequest,
    RunStore,
    Supervisor,
)
from inspection_platform.contracts import RunSpec, sha256_file


def run_spec() -> RunSpec:
    return RunSpec(
        model_family="patchcore",
        category="can",
        seed=42,
        config={"batch_size": 4, "oom_fallback_batch_size": 1},
        dataset_manifest_sha256="a" * 64,
    )


def test_completed_matching_run_is_skipped(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    store.write_completed(spec, valid_artifacts=True)

    plan = Supervisor(store).plan([spec])

    assert plan.skipped == [spec.identity]
    assert plan.pending == []


def test_changed_config_never_reuses_checkpoint(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    store.write_checkpoint(spec)
    changed = spec.model_copy(update={"config": {"batch_size": 2}})

    plan = Supervisor(store).plan([changed])

    assert plan.resumed == []
    assert plan.pending == [changed.identity]


def test_matching_valid_checkpoint_is_resumed(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    store.write_checkpoint(spec)

    plan = Supervisor(store).plan([spec])

    assert plan.resumed == [spec.identity]


def test_mismatched_artifact_is_quarantined_without_overwrite(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    original = store.write_completed(spec, valid_artifacts=False)

    plan = Supervisor(store).plan([spec])

    assert plan.quarantined == [spec.identity]
    assert plan.pending == [spec.identity]
    assert not original.exists()
    quarantines = tuple(tmp_path.glob(f"{spec.identity}.quarantine-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "record.json").is_file()


class SuccessfulRunner:
    def __init__(self) -> None:
        self.requests: list[RunRequest] = []

    def __call__(self, request: RunRequest) -> ExecutionResult:
        self.requests.append(request)
        result = request.run_dir / "metrics" / "result.json"
        result.write_text("{}\n", encoding="utf-8")
        return ExecutionResult(
            exit_code=0,
            artifacts={"metrics/result.json": sha256_file(result)},
            latency_ms=12.5,
            peak_vram_mib=1024.0,
        )


def test_run_resumes_only_the_matching_verified_checkpoint(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    checkpoint = store.write_checkpoint(spec)
    runner = SuccessfulRunner()

    summary = Supervisor(store, runner=runner, disk_probe=lambda _path: 100 * 1024**3).run(
        [spec]
    )

    assert summary.completed == [spec.identity]
    assert summary.resumed == [spec.identity]
    assert runner.requests[0].resume_checkpoint == checkpoint
    assert store.load_record(store.run_dir(spec)).status == "completed"


def test_first_oom_uses_only_predeclared_fallback_as_a_second_attempt(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    requests: list[RunRequest] = []

    def runner(request: RunRequest) -> ExecutionResult:
        requests.append(request)
        if request.attempt == 1:
            return ExecutionResult(exit_code=1, error_kind="oom", message="CUDA out of memory")
        result = request.run_dir / "metrics" / "result.json"
        result.write_text("{}\n", encoding="utf-8")
        return ExecutionResult(
            exit_code=0,
            artifacts={"metrics/result.json": sha256_file(result)},
        )

    summary = Supervisor(store, runner=runner, disk_probe=lambda _path: 100 * 1024**3).run(
        [spec]
    )

    assert summary.completed == [spec.identity]
    assert [request.attempt for request in requests] == [1, 2]
    assert [request.effective_config["batch_size"] for request in requests] == [4, 1]
    rows = (store.run_dir(spec) / "heartbeat.jsonl").read_text(encoding="utf-8")
    assert '"event": "oom_retry"' in rows


def test_second_oom_fails_run_and_stops_remaining_queue(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    first = run_spec()
    second = first.model_copy(update={"category": "fabric"})

    def runner(_request: RunRequest) -> ExecutionResult:
        return ExecutionResult(exit_code=1, error_kind="oom", message="CUDA out of memory")

    summary = Supervisor(store, runner=runner, disk_probe=lambda _path: 100 * 1024**3).run(
        [first, second]
    )

    assert summary.failed == [first.identity]
    assert summary.stopped == [second.identity]
    record = store.load_record(store.run_dir(first))
    assert record.status == "failed"
    assert record.attempt == 2
    assert record.error is not None and "second OOM" in record.error

    calls = 0

    def must_not_run(_request: RunRequest) -> ExecutionResult:
        nonlocal calls
        calls += 1
        return ExecutionResult(exit_code=0)

    rerun = Supervisor(
        store, runner=must_not_run, disk_probe=lambda _path: 100 * 1024**3
    ).run([first])
    assert rerun.failed == [first.identity]
    assert calls == 0


def test_retryable_subprocess_crash_is_stopped_then_runs_fresh_on_restart(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()

    first = Supervisor(
        store,
        runner=lambda _request: ExecutionResult(
            exit_code=7,
            error_kind="subprocess",
            message="worker crashed",
        ),
        disk_probe=lambda _path: 100 * 1024**3,
    ).run([spec])

    assert first.failed == [spec.identity]
    assert store.load_record(store.run_dir(spec)).status == "stopped"
    runner = SuccessfulRunner()
    second = Supervisor(
        store, runner=runner, disk_probe=lambda _path: 100 * 1024**3
    ).run([spec])
    assert second.completed == [spec.identity]
    assert len(runner.requests) == 1


def test_runner_checksum_mismatch_is_quarantined_and_stops_queue(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()

    def runner(request: RunRequest) -> ExecutionResult:
        result = request.run_dir / "metrics" / "result.json"
        result.write_text("tampered\n", encoding="utf-8")
        return ExecutionResult(
            exit_code=0,
            artifacts={"metrics/result.json": "f" * 64},
        )

    summary = Supervisor(store, runner=runner, disk_probe=lambda _path: 100 * 1024**3).run(
        [spec]
    )

    assert summary.failed == [spec.identity]
    assert summary.quarantined == [spec.identity]
    assert not store.run_dir(spec).exists()
    assert len(tuple(tmp_path.glob(f"{spec.identity}.quarantine-*"))) == 1


def test_truncated_record_is_quarantined_before_fresh_execution(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    run_dir = store.initialize(spec)
    (run_dir / "record.json").write_text("{", encoding="utf-8")
    runner = SuccessfulRunner()

    summary = Supervisor(store, runner=runner, disk_probe=lambda _path: 100 * 1024**3).run(
        [spec]
    )

    assert summary.quarantined == [spec.identity]
    assert summary.completed == [spec.identity]
    assert len(tuple(tmp_path.glob(f"{spec.identity}.quarantine-*"))) == 1


def test_completed_record_captures_formal_reproducibility_evidence(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    spec = run_spec()
    runner = SuccessfulRunner()
    timestamps = iter((100.0, 112.5))

    Supervisor(
        store,
        runner=runner,
        disk_probe=lambda _path: 100 * 1024**3,
        code_revision="c0725f1f2d1efe25c0d3d6f5f3752321d1bb7183",
        environment_lock_sha256="b" * 64,
        model_revision=lambda item: f"anomalib:2.5.0/{item.model_family}",
        clock=lambda: next(timestamps),
    ).run([spec])

    record = store.load_record(store.run_dir(spec))
    assert record.code_revision == "c0725f1f2d1efe25c0d3d6f5f3752321d1bb7183"
    assert record.config_sha256 is not None and len(record.config_sha256) == 64
    assert record.environment_lock_sha256 == "b" * 64
    assert record.model_revision == "anomalib:2.5.0/patchcore"
    assert record.started_at == 100.0
    assert record.finished_at == 112.5
    assert record.latency_ms == 12.5
    assert record.peak_vram_mib == 1024.0
    assert record.exit_code == 0
