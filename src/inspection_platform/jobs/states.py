from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.COMPLETED_WITH_ERRORS,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.COMPLETED_WITH_ERRORS: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


def can_transition(source: JobStatus, target: JobStatus) -> bool:
    return target in _TRANSITIONS[source]


__all__ = ["JobStatus", "can_transition"]
