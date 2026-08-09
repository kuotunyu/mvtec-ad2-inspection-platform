from __future__ import annotations

from inspection_platform.contracts.models import BundleFile, ModelBundleManifest
from inspection_platform.inference.mock import MockRuntime
from inspection_platform.jobs.states import JobStatus
from inspection_platform.worker.runner import WorkerRunner, WorkItem


def test_mock_backend_workflow_completes() -> None:
    manifest = ModelBundleManifest(
        category="can",
        runtime_kind="mock",
        model_family=None,
        evaluation_scope="synthetic-ci-only",
        files=(BundleFile(path="mock", sha256="0" * 64, size=0),),
    )
    runtime = MockRuntime.load(manifest)
    result = WorkerRunner(runtime, [WorkItem("one", b"image")]).run_once()
    assert result.status is JobStatus.COMPLETED
    assert result.succeeded == 1
