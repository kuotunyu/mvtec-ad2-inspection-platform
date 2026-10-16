from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
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
    observed = _utc(now)
    owned = [
        Job.id == job_id,
        Job.state == "RUNNING",
        Job.worker_id == worker_id,
        Job.lease_expires_at > observed,
    ]
    if expected_attempt is not None:
        owned.append(Job.attempt == expected_attempt)
    with session_factory() as session, session.begin():
        renewed = cast(
            CursorResult[Any],
            session.execute(
                update(Job)
                .where(*owned)
                .values(
                    heartbeat_at=observed,
                    lease_expires_at=observed + timedelta(seconds=lease_seconds),
                )
                .execution_options(synchronize_session=False)
            ),
        )
        return renewed.rowcount == 1


def recover_expired_leases(session_factory: Callable[[], Session], now: datetime) -> int:
    with session_factory() as session, session.begin():
        recovered = cast(
            CursorResult[Any],
            session.execute(
                update(Job)
                .where(Job.state == "RUNNING", Job.lease_expires_at <= _utc(now))
                .values(state="queued", worker_id=None, lease_expires_at=None, heartbeat_at=None)
                .execution_options(synchronize_session=False)
            ),
        )
        return recovered.rowcount


__all__ = ["claim_next_job", "recover_expired_leases", "renew_lease"]
