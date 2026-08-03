from __future__ import annotations

import sys
from pathlib import Path

from experiments.orchestration.health import HeartbeatLog
from experiments.orchestration.supervisor import (
    RunRequest,
    RunStore,
    SubprocessExecutor,
)
from inspection_platform.contracts import RunSpec


def request(tmp_path: Path) -> RunRequest:
    spec = RunSpec(
        model_family="patchcore",
        category="can",
        seed=42,
        config={"batch_size": 1, "oom_fallback_batch_size": None},
        dataset_manifest_sha256="a" * 64,
    )
    run_dir = RunStore(tmp_path).initialize(spec)
    return RunRequest(
        spec=spec,
        effective_config=dict(spec.config),
        attempt=1,
        run_dir=run_dir,
        resume_checkpoint=None,
        heartbeat=HeartbeatLog(
            run_dir / "heartbeat.jsonl",
            disk_probe=lambda _path: 100 * 1024**3,
            gpu_probe=lambda: {},
        ),
    )


def test_subprocess_executor_validates_worker_result_and_adds_logs(tmp_path: Path) -> None:
    run_request = request(tmp_path)
    script = """
import hashlib, json
from pathlib import Path
artifact = Path('metrics/result.json')
artifact.write_text('{}\\n', encoding='utf-8')
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
Path('worker-result.json').write_text(json.dumps({
    'exit_code': 0,
    'artifacts': {'metrics/result.json': digest},
    'error_kind': None,
    'message': None,
    'latency_ms': 1.0,
    'peak_vram_mib': 2.0,
}), encoding='utf-8')
"""
    executor = SubprocessExecutor(
        lambda _request: (sys.executable, "-c", script),
        heartbeat_interval_seconds=0.1,
    )

    result = executor(run_request)

    assert result.exit_code == 0
    assert result.error_kind is None
    assert set(result.artifacts) == {
        "metrics/result.json",
        "worker-result.json",
        "worker.stderr.log",
        "worker.stdout.log",
    }


def test_truncated_worker_result_is_an_integrity_failure(tmp_path: Path) -> None:
    run_request = request(tmp_path)
    script = "from pathlib import Path; Path('worker-result.json').write_text('{')"
    executor = SubprocessExecutor(
        lambda _request: (sys.executable, "-c", script),
        heartbeat_interval_seconds=0.1,
    )

    result = executor(run_request)

    assert result.exit_code == 0
    assert result.error_kind == "checksum_mismatch"
    assert result.message is not None and "unreadable" in result.message


def test_missing_worker_result_preserves_nonzero_exit_code(tmp_path: Path) -> None:
    run_request = request(tmp_path)
    executor = SubprocessExecutor(
        lambda _request: (sys.executable, "-c", "raise SystemExit(7)"),
        heartbeat_interval_seconds=0.1,
    )

    result = executor(run_request)

    assert result.exit_code == 7
    assert result.error_kind == "subprocess"
