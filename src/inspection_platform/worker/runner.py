from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Protocol

from inspection_platform.jobs.states import JobStatus


class Runtime(Protocol):
    def predict(self, image: bytes, *, input_id: str) -> object: ...


@dataclass
class WorkItem:
    id: str
    image: bytes
    completed: bool = False


@dataclass(frozen=True)
class WorkResult:
    status: JobStatus
    succeeded: int
    failed: int


class WorkerRunner:
    def __init__(self, runtime: Runtime, items: list[WorkItem]) -> None:
        self.runtime = runtime
        self.items = items

    def run_once(self) -> WorkResult:
        succeeded = 0
        failed = 0
        for item in self.items:
            if item.completed:
                continue
            try:
                self.runtime.predict(item.image, input_id=item.id)
            except Exception:
                failed += 1
                continue
            item.completed = True
            succeeded += 1
        status = JobStatus.COMPLETED_WITH_ERRORS if failed else JobStatus.COMPLETED
        return WorkResult(status, succeeded, failed)

    def serve(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            self.run_once()
            stop_event.wait(0.1)


__all__ = ["WorkItem", "WorkResult", "WorkerRunner"]
