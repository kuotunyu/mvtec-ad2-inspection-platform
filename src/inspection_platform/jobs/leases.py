from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from inspection_platform.db.models import Job

LEASE_SECONDS = 120


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)


def claim_next_job(
    session_factory: Callable[[], Session],
    worker_id: str,
    now: datetime,
    *,
    lease_seconds: int = LEASE_SECONDS,
) -> Job | None:
    observed = _utc(now)
    eligible = or_(
        Job.state == "queued",
        (Job.state == "RUNNING") & (Job.lease_expires_at <= observed),
    )
    candidate = select(Job.id).where(eligible).order_by(Job.created_at).limit(1).scalar_subquery()
    with session_factory() as session, session.begin():
        job_id = session.scalar(
            update(Job)
            .where(Job.id == candidate)
            .values(
                state="RUNNING",
                worker_id=worker_id,
                heartbeat_at=observed,
                lease_expires_at=observed + timedelta(seconds=lease_seconds),
                attempt=Job.attempt + 1,
            )
            .returning(Job.id)
        )
        if job_id is None:
            return None
        job = session.get(Job, job_id)
        if job is None:
            raise RuntimeError("claimed job disappeared before it could be loaded")
        return job


def renew_lease(
    session_factory: Callable[[], Session],
    job_id: str,
    worker_id: str,
    now: datetime,
    *,
    lease_seconds: int = LEASE_SECONDS,
    expected_attempt: int | None = None,
) -> bool:
    with session_factory() as session, session.begin():
        job = session.get(Job, job_id)
        if (
            job is None
            or job.state != "RUNNING"
            or job.worker_id != worker_id
            or (expected_attempt is not None and job.attempt != expected_attempt)
            or job.lease_expires_at is None
            or job.lease_expires_at <= _utc(now)
        ):
            return False
        job.heartbeat_at = _utc(now)
        job.lease_expires_at = _utc(now) + timedelta(seconds=lease_seconds)
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
