from __future__ import annotations

import pytest

from inspection_platform.jobs.states import JobStatus, can_transition


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (JobStatus.QUEUED, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
        (JobStatus.RUNNING, JobStatus.COMPLETED_WITH_ERRORS),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.QUEUED, JobStatus.CANCELLED),
        (JobStatus.RUNNING, JobStatus.CANCELLED),
    ],
)
def test_legal_transition(source: JobStatus, target: JobStatus) -> None:
    assert can_transition(source, target)


def test_completed_job_cannot_restart() -> None:
    assert not can_transition(JobStatus.COMPLETED, JobStatus.RUNNING)
