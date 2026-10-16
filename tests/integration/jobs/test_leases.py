from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, Event, Thread, get_ident
from typing import Any
from uuid import uuid4

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


T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
HOLD_TIMEOUT = 10.0


def _naive(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(tzinfo=None)


class _HoldBeforeJobUpdate:
    """Hold one thread immediately before its first ``UPDATE jobs`` statement.

    This pins the interleaving that the lease writers have to survive: a
    competing transaction commits between the moment a writer decides what to
    do and the moment its write reaches the database.

    The hold is gated on thread identity, so the releasing thread's own
    statements never block, and it arms at most once, so a writer that emits
    several UPDATEs is only held on the first. Every wait is bounded. Together
    these make the helper safe against both writer shapes -- a guard ``SELECT``
    followed by an unconditional ``UPDATE``, or a single conditional
    ``UPDATE`` -- and it cannot deadlock even if no ``UPDATE`` is ever emitted:
    the waiter times out and the assertion fails instead of hanging. No test
    depends on sleeping or on elapsed wall-clock time.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._held_thread: int | None = None
        self._reached = Event()
        self._released = Event()

    def __enter__(self) -> _HoldBeforeJobUpdate:
        event.listen(self._engine, "before_cursor_execute", self._before_cursor_execute)
        return self

    def __exit__(self, *_exc: object) -> None:
        self._released.set()
        event.remove(self._engine, "before_cursor_execute", self._before_cursor_execute)

    def arm(self) -> None:
        """Mark the calling thread as the one to hold."""
        self._held_thread = get_ident()

    def _before_cursor_execute(
        self,
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if get_ident() != self._held_thread or self._reached.is_set():
            return
        if not statement.lstrip().upper().startswith("UPDATE JOBS"):
            return
        self._reached.set()
        self._released.wait(timeout=HOLD_TIMEOUT)

    def wait_until_held(self) -> bool:
        return self._reached.wait(timeout=HOLD_TIMEOUT)

    def release(self) -> None:
        self._released.set()


def _run_held(
    engine: Engine,
    held: Callable[[], None],
    *,
    while_held: Callable[[], None],
) -> None:
    """Run ``held`` in a thread paused before its write, then ``while_held``."""
    with _HoldBeforeJobUpdate(engine) as hold:

        def target() -> None:
            hold.arm()
            held()

        worker = Thread(target=target, name="held-lease-writer")
        worker.start()
        try:
            assert hold.wait_until_held(), "writer never reached its UPDATE"
            while_held()
        finally:
            hold.release()
            worker.join(timeout=HOLD_TIMEOUT)
        assert not worker.is_alive()


def _engine_of(repos: Repositories) -> Engine:
    engine = repos.session_factory.kw["bind"]
    assert isinstance(engine, Engine)
    return engine


def test_renew_lease_rejects_a_takeover_that_commits_before_the_write(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    claimed = claim_next_job(repos.session_factory, "worker-a", T0, lease_seconds=10)
    assert claimed is not None
    assert claimed.attempt == 1

    renewed: list[bool] = []
    takeover: list[int] = []

    def renew_as_worker_a() -> None:
        renewed.append(
            renew_lease(
                repos.session_factory,
                job.id,
                "worker-a",
                T0 + timedelta(seconds=9),
                lease_seconds=10,
                expected_attempt=1,
            )
        )

    def steal_as_worker_b() -> None:
        stolen = claim_next_job(
            repos.session_factory, "worker-b", T0 + timedelta(seconds=11), lease_seconds=10
        )
        assert stolen is not None
        takeover.append(stolen.attempt)

    _run_held(_engine_of(repos), renew_as_worker_a, while_held=steal_as_worker_b)

    assert takeover == [2]
    assert renewed == [False], "renew_lease told an evicted worker it still owns the job"
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.worker_id == "worker-b"
        assert current.attempt == 2
        assert current.lease_expires_at == _naive(T0 + timedelta(seconds=21))
        assert current.heartbeat_at == _naive(T0 + timedelta(seconds=11))


def test_recover_expired_leases_spares_a_lease_reclaimed_before_the_write(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    claimed = claim_next_job(repos.session_factory, "worker-a", T0, lease_seconds=10)
    assert claimed is not None

    recovered: list[int] = []
    takeover: list[int] = []

    def recover_at_expiry() -> None:
        recovered.append(recover_expired_leases(repos.session_factory, T0 + timedelta(seconds=11)))

    def reclaim_as_worker_b() -> None:
        stolen = claim_next_job(
            repos.session_factory, "worker-b", T0 + timedelta(seconds=11), lease_seconds=10
        )
        assert stolen is not None
        takeover.append(stolen.attempt)

    _run_held(_engine_of(repos), recover_at_expiry, while_held=reclaim_as_worker_b)

    assert takeover == [2]
    assert recovered == [0], "recovery destroyed a lease that was unexpired when it wrote"
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.state == "RUNNING"
        assert current.worker_id == "worker-b"
        assert current.attempt == 2
        assert current.lease_expires_at == _naive(T0 + timedelta(seconds=21))


def test_renew_lease_rejects_the_same_worker_on_a_new_attempt_generation(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    first = claim_next_job(repos.session_factory, "worker-a", T0, lease_seconds=10)
    assert first is not None and first.attempt == 1
    assert recover_expired_leases(repos.session_factory, T0 + timedelta(seconds=11)) == 1
    second = claim_next_job(
        repos.session_factory, "worker-a", T0 + timedelta(seconds=12), lease_seconds=10
    )
    assert second is not None
    assert second.attempt == 2

    # Matching worker_id must not be enough to satisfy the attempt fence.
    assert not renew_lease(
        repos.session_factory,
        job.id,
        "worker-a",
        T0 + timedelta(seconds=13),
        lease_seconds=10,
        expected_attempt=1,
    )
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.lease_expires_at == _naive(T0 + timedelta(seconds=22))

    # The current generation still renews, and an offset-aware clock is
    # normalized to naive UTC exactly as before.
    assert renew_lease(
        repos.session_factory,
        job.id,
        "worker-a",
        (T0 + timedelta(seconds=13)).astimezone(timezone(timedelta(hours=9))),
        lease_seconds=10,
        expected_attempt=2,
    )
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.heartbeat_at == _naive(T0 + timedelta(seconds=13))
        assert current.lease_expires_at == _naive(T0 + timedelta(seconds=23))


def test_renew_lease_rejects_an_expired_lease(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    assert claim_next_job(repos.session_factory, "worker-a", T0, lease_seconds=10) is not None

    # The expiry instant itself is already too late, as before the fix.
    assert not renew_lease(
        repos.session_factory, job.id, "worker-a", T0 + timedelta(seconds=10), lease_seconds=10
    )
    assert not renew_lease(
        repos.session_factory, job.id, "worker-a", T0 + timedelta(seconds=11), lease_seconds=10
    )
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.lease_expires_at == _naive(T0 + timedelta(seconds=10))
        assert current.heartbeat_at == _naive(T0)


def test_renew_lease_rejects_a_job_that_is_not_running(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    assert claim_next_job(repos.session_factory, "worker-a", T0, lease_seconds=10) is not None
    assert recover_expired_leases(repos.session_factory, T0 + timedelta(seconds=11)) == 1

    assert not renew_lease(
        repos.session_factory, job.id, "worker-a", T0 + timedelta(seconds=12), lease_seconds=10
    )
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.state == "queued"
        assert current.worker_id is None
        assert current.lease_expires_at is None
        assert current.heartbeat_at is None


def test_renew_lease_rejects_a_different_owner(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    job = repos.jobs.create(category="can", image_count=1)
    assert claim_next_job(repos.session_factory, "worker-a", T0, lease_seconds=10) is not None

    assert not renew_lease(
        repos.session_factory, job.id, "worker-b", T0 + timedelta(seconds=5), lease_seconds=10
    )
    with repos.session_factory() as session:
        current = session.get(type(job), job.id)
        assert current is not None
        assert current.worker_id == "worker-a"
        assert current.lease_expires_at == _naive(T0 + timedelta(seconds=10))
        assert current.heartbeat_at == _naive(T0)


def test_renew_lease_returns_false_for_an_unknown_job(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    assert not renew_lease(repos.session_factory, str(uuid4()), "worker-a", T0, lease_seconds=10)


def test_recover_expired_leases_counts_only_expired_running_leases(tmp_path: Path) -> None:
    repos = _repos(tmp_path)
    for _ in range(3):
        repos.jobs.create(category="can", image_count=1)
    stale = T0 - timedelta(minutes=5)
    # The live lease is taken first: claim_next_job orders candidates by
    # created_at and treats an expired lease as claimable, so a later claim
    # would otherwise steal one of the stale jobs instead of a queued one.
    live = claim_next_job(repos.session_factory, "worker-c", T0, lease_seconds=600)
    first = claim_next_job(repos.session_factory, "worker-a", stale, lease_seconds=10)
    second = claim_next_job(repos.session_factory, "worker-b", stale, lease_seconds=10)
    assert first is not None and second is not None and live is not None

    assert recover_expired_leases(repos.session_factory, T0) == 2
    assert recover_expired_leases(repos.session_factory, T0) == 0

    with repos.session_factory() as session:
        for expired_id in (first.id, second.id):
            recovered_job = session.get(type(live), expired_id)
            assert recovered_job is not None
            assert recovered_job.state == "queued"
            assert recovered_job.worker_id is None
            assert recovered_job.lease_expires_at is None
            assert recovered_job.heartbeat_at is None
        untouched = session.get(type(live), live.id)
        assert untouched is not None
        assert untouched.state == "RUNNING"
        assert untouched.worker_id == "worker-c"
        assert untouched.lease_expires_at == _naive(T0 + timedelta(seconds=600))
