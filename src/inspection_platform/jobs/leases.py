from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from inspection_platform.db.models import Job

LEASE_SECONDS = 120


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)


def claim_next_job(
    session_factory: Callable[[], Session], worker_id: str, now: datetime
) -> Job | None:
    with session_factory() as session, session.begin():
        job = session.scalar(
            select(Job)
            .where(
                or_(
                    Job.state == "queued",
                    (Job.state == "RUNNING") & (Job.lease_expires_at <= _utc(now)),
                )
            )
            .order_by(Job.created_at)
            .limit(1)
        )
        if job is None:
            return None
        job.state = "RUNNING"
        job.worker_id = worker_id
        job.heartbeat_at = _utc(now)
        job.lease_expires_at = _utc(now) + timedelta(seconds=LEASE_SECONDS)
        job.attempt += 1
        session.flush()
        return job


def renew_lease(
    session_factory: Callable[[], Session], job_id: str, worker_id: str, now: datetime
) -> bool:
    with session_factory() as session, session.begin():
        job = session.get(Job, job_id)
        if (
            job is None
            or job.state != "RUNNING"
            or job.worker_id != worker_id
            or job.lease_expires_at is None
            or job.lease_expires_at <= _utc(now)
        ):
            return False
        job.heartbeat_at = _utc(now)
        job.lease_expires_at = _utc(now) + timedelta(seconds=LEASE_SECONDS)
        return True


def recover_expired_leases(session_factory: Callable[[], Session], now: datetime) -> int:
    with session_factory() as session, session.begin():
        jobs = list(
            session.scalars(
                select(Job).where(Job.state == "RUNNING", Job.lease_expires_at <= _utc(now))
            )
        )
        for job in jobs:
            job.state = "queued"
            job.worker_id = None
            job.lease_expires_at = None
            job.heartbeat_at = None
        return len(jobs)


__all__ = ["claim_next_job", "recover_expired_leases", "renew_lease"]
