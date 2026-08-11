from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Thread
from typing import Any

from sqlalchemy import Engine, event

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


def test_concurrent_workers_claim_a_job_atomically(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    engine = repos.session_factory.kw["bind"]
    assert isinstance(engine, Engine)
    ready_to_claim = Barrier(2)

    def pause_before_claim_update(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("UPDATE jobs"):
            ready_to_claim.wait(timeout=2)

    event.listen(engine, "before_cursor_execute", pause_before_claim_update)
    results: list[str | None] = []
    errors: list[Exception] = []

    def claim(worker_id: str) -> None:
        try:
            claimed = claim_next_job(repos.session_factory, worker_id, datetime.now(UTC))
            results.append(claimed.id if claimed else None)
        except Exception as exc:
            errors.append(exc)

    workers = [Thread(target=claim, args=(worker_id,)) for worker_id in ("worker-a", "worker-b")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)
    event.remove(engine, "before_cursor_execute", pause_before_claim_update)

    assert errors == []
    assert results.count(job.id) == 1
    assert results.count(None) == 1


def test_expired_lease_is_recovered_idempotently(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    repos.jobs.create(category="can", image_count=1)
    now = datetime.now(UTC)
    claim_next_job(repos.session_factory, "worker-a", now - timedelta(minutes=5))
    assert recover_expired_leases(repos.session_factory, now) == 1
    assert recover_expired_leases(repos.session_factory, now) == 0


def test_configured_lease_duration_is_used_for_claim_and_renewal(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    now = datetime.now(UTC)

    claimed = claim_next_job(repos.session_factory, "worker-a", now, lease_seconds=17)
    assert claimed is not None
    assert claimed.lease_expires_at == now.replace(tzinfo=None) + timedelta(seconds=17)
    assert renew_lease(
        repos.session_factory,
        job.id,
        "worker-a",
        now + timedelta(seconds=5),
        lease_seconds=23,
    )
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.lease_expires_at == now.replace(tzinfo=None) + timedelta(seconds=28)


def test_lease_renewal_rejects_a_stale_attempt_generation(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    now = datetime.now(UTC)
    claimed = claim_next_job(repos.session_factory, "worker-a", now)
    assert claimed is not None

    assert not renew_lease(
        repos.session_factory,
        job.id,
        "worker-a",
        now + timedelta(seconds=1),
        expected_attempt=claimed.attempt + 1,
    )
