from __future__ import annotations

from inspection_platform.jobs.states import JobStatus
from inspection_platform.worker.runner import WorkerRunner, WorkItem


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def predict(self, image: bytes, *, input_id: str) -> object:
        self.calls.append(input_id)
        if image == b"broken":
            raise ValueError("bad image")
        return {"id": input_id}


def test_resume_skips_completed_images() -> None:
    runtime = FakeRuntime()
    items = [WorkItem("first", b"ok", completed=True), WorkItem("second", b"ok")]
    result = WorkerRunner(runtime, items).run_once()
    assert runtime.calls == ["second"]
    assert result.status is JobStatus.COMPLETED


def test_one_bad_image_yields_partial_completion() -> None:
    runtime = FakeRuntime()
    items = [WorkItem("first", b"ok"), WorkItem("broken", b"broken")]
    result = WorkerRunner(runtime, items).run_once()
    assert result.status is JobStatus.COMPLETED_WITH_ERRORS
    assert result.succeeded == 1 and result.failed == 1
