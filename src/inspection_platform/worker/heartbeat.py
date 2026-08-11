from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event, Thread
from typing import Protocol

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from inspection_platform.db.models import WorkerHeartbeat


class LeaseRenewer(Protocol):
    def __call__(self, job_id: str, worker_id: str, now: datetime) -> bool: ...


def heartbeat(renewer: LeaseRenewer, job_id: str, worker_id: str, now: datetime) -> bool:
    return renewer(job_id, worker_id, now)


def record_worker_heartbeat(
    session_factory: Callable[[], Session],
    worker_id: str,
    *,
    status: str,
    now: datetime | None = None,
) -> None:
    observed = now or datetime.now(UTC)
    with session_factory() as session, session.begin():
        session.execute(
            sqlite_insert(WorkerHeartbeat)
            .values(
                worker_id=worker_id,
                started_at=observed,
                heartbeat_at=observed,
                status=status,
            )
            .on_conflict_do_update(
                index_elements=[WorkerHeartbeat.worker_id],
                set_={"heartbeat_at": observed, "status": status},
            )
        )


class LeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the job it is processing."""


class LeaseHeartbeat:
    def __init__(self, renew: Callable[[], bool], *, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        self._renew = renew
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._lost = Event()
        self._thread = Thread(target=self._run, name="inspection-lease-heartbeat", daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                if not self._renew():
                    self._lost.set()
                    return
            except Exception:
                self._lost.set()
                return

    def __enter__(self) -> LeaseHeartbeat:
        self._thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self._stop.set()
        self._thread.join(timeout=max(self._interval_seconds * 2, 1.0))

    def assert_owned(self) -> None:
        if self._lost.is_set():
            raise LeaseLostError("worker lease ownership was lost")

    def wait_until_lost(self, timeout: float) -> bool:
        return self._lost.wait(timeout)


__all__ = ["LeaseHeartbeat", "LeaseLostError", "heartbeat", "record_worker_heartbeat"]
