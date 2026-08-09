from __future__ import annotations

from datetime import datetime
from typing import Protocol


class LeaseRenewer(Protocol):
    def __call__(self, job_id: str, worker_id: str, now: datetime) -> bool: ...


def heartbeat(renewer: LeaseRenewer, job_id: str, worker_id: str, now: datetime) -> bool:
    return renewer(job_id, worker_id, now)


__all__ = ["heartbeat"]
