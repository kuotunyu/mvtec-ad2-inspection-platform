from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.repositories import Repositories
from inspection_platform.jobs.leases import claim_next_job, recover_expired_leases, renew_lease
from inspection_platform.settings import Settings


def _repos(tmp_path: Path) -> Repositories:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
    )
    return Repositories(create_engine_and_session(settings))


def test_two_workers_cannot_claim_same_job(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    now = datetime.now(UTC)
    first = claim_next_job(repos.session_factory, "worker-a", now)
    second = claim_next_job(repos.session_factory, "worker-b", now)
    assert first is not None and first.id == job.id
    assert second is None
    assert renew_lease(repos.session_factory, job.id, "worker-a", now + timedelta(seconds=10))


def test_expired_lease_is_recovered_idempotently(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    repos.jobs.create(category="can", image_count=1)
    now = datetime.now(UTC)
    claim_next_job(repos.session_factory, "worker-a", now - timedelta(minutes=5))
    assert recover_expired_leases(repos.session_factory, now) == 1
    assert recover_expired_leases(repos.session_factory, now) == 0
