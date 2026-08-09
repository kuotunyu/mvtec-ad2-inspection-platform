from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from inspection_platform.db.models import AuditEvent, Job, Prediction

from .conftest import SystemHarness


def test_expired_worker_recovery_is_idempotent(system_harness: SystemHarness) -> None:
    created = system_harness.upload("clean-control.png")
    assert system_harness.worker.process_once()
    with system_harness.worker.sessions() as session, session.begin():
        job = session.get(Job, created["id"])
        assert job is not None
        job.state = "RUNNING"
        job.worker_id = "dead-worker"
        job.heartbeat_at = datetime.now(UTC) - timedelta(minutes=5)
        job.lease_expires_at = datetime.now(UTC) - timedelta(minutes=4)
    assert system_harness.worker.process_once()
    with system_harness.worker.sessions() as session:
        predictions = session.scalar(select(func.count()).select_from(Prediction))
        completions = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.resource_id == created["id"],
                AuditEvent.action == "job.completed",
            )
        )
        job = session.get(Job, created["id"])
        assert predictions == 1
        assert completions == 1
        assert job is not None and job.state == "COMPLETED"
