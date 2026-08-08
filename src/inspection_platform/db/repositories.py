from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, Job


def _now() -> datetime:
    return datetime.now(UTC)


class JobRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def create(self, *, category: str, image_count: int) -> Job:
        with self._session_factory() as session, session.begin():
            job = Job(
                id=str(uuid4()),
                category=category,
                image_count=image_count,
                state="queued",
                created_at=_now(),
            )
            session.add(job)
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    action="job.created",
                    resource_id=job.id,
                    created_at=job.created_at,
                )
            )
            session.flush()
            return job


class AuditRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def list_for_resource(self, resource_id: str) -> list[AuditEvent]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.resource_id == resource_id)
                    .order_by(AuditEvent.created_at)
                )
            )


class Repositories:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory
        self.jobs = JobRepository(session_factory)
        self.audit = AuditRepository(session_factory)


__all__ = ["AuditRepository", "JobRepository", "Repositories"]
