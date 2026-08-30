from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

from pytest import MonkeyPatch
from sqlalchemy import func, select

import inspection_platform.worker.service as worker_service
from inspection_platform.db.models import AuditEvent, Job, Prediction
from inspection_platform.inference.runtime import InferenceRuntime
from inspection_platform.registry.repository import ModelRegistry
from inspection_platform.retention import DeletionScopeError
from inspection_platform.worker.service import WorkerService

from .conftest import SystemHarness


def test_worker_ready_file_uses_platform_temp_directory(
    system_harness: SystemHarness, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(worker_service, "gettempdir", lambda: str(tmp_path), raising=False)
    stop = Event()
    stop.set()

    WorkerService(system_harness.settings, worker_id="portable-worker").serve(stop)

    assert (tmp_path / "inspection-worker.ready").read_text(encoding="utf-8") == "portable-worker"


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


def test_slow_inference_renews_the_job_lease(
    system_harness: SystemHarness, monkeypatch: MonkeyPatch
) -> None:
    created = system_harness.upload("clean-control.png")
    original_load = InferenceRuntime.load
    loaded = original_load(
        ModelRegistry(system_harness.settings.model_registry_root).register(
            system_harness.settings.model_registry_root / "categories" / "can" / "manifest.json"
        )
    )
    started, release = Event(), Event()

    class SlowRuntime:
        def predict_with_map(self, image: bytes, *, input_id: str) -> object:
            started.set()
            assert release.wait(2)
            return loaded.predict_with_map(image, input_id=input_id)

    monkeypatch.setattr(InferenceRuntime, "load", lambda *_args, **_kwargs: SlowRuntime())
    settings = system_harness.settings.model_copy(
        update={"lease_seconds": 2, "heartbeat_seconds": 0.05}
    )
    worker = WorkerService(settings, worker_id="slow-worker")
    thread = Thread(target=worker.process_once)
    thread.start()
    assert started.wait(1)
    with worker.sessions() as session:
        job = session.get(Job, created["id"])
        assert job is not None
        first_heartbeat = job.heartbeat_at
    deadline = monotonic() + 1
    renewed = False
    while monotonic() < deadline:
        with worker.sessions() as session:
            job = session.get(Job, created["id"])
            renewed = bool(job and job.heartbeat_at and job.heartbeat_at != first_heartbeat)
        if renewed:
            break
        sleep(0.02)
    release.set()
    thread.join(2)
    assert renewed
    assert not thread.is_alive()


def test_cancelled_job_fences_stale_worker_prediction_commit(
    system_harness: SystemHarness, monkeypatch: MonkeyPatch
) -> None:
    created = system_harness.upload("clean-control.png")
    original_load = InferenceRuntime.load
    loaded = original_load(
        ModelRegistry(system_harness.settings.model_registry_root).register(
            system_harness.settings.model_registry_root / "categories" / "can" / "manifest.json"
        )
    )
    started, release = Event(), Event()

    class BlockedRuntime:
        def predict_with_map(self, image: bytes, *, input_id: str) -> object:
            started.set()
            assert release.wait(2)
            return loaded.predict_with_map(image, input_id=input_id)

    monkeypatch.setattr(InferenceRuntime, "load", lambda *_args, **_kwargs: BlockedRuntime())
    worker = WorkerService(system_harness.settings, worker_id="stale-worker")
    thread = Thread(target=worker.process_once)
    thread.start()
    assert started.wait(1)
    cancelled = system_harness.client.post(f"/api/v1/jobs/{created['id']}/cancel")
    assert cancelled.status_code == 200
    release.set()
    thread.join(2)

    with worker.sessions() as session:
        job = session.get(Job, created["id"])
        predictions = session.scalar(select(func.count()).select_from(Prediction))
        completions = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.resource_id == created["id"],
                AuditEvent.action == "job.completed",
            )
        )
    assert not thread.is_alive()
    assert job is not None and job.state == "CANCELLED"
    assert predictions == 0
    assert completions == 0


def test_retention_failure_does_not_terminate_worker_service(
    system_harness: SystemHarness, monkeypatch: MonkeyPatch
) -> None:
    stop = Event()
    calls = 0

    def fail_retention(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            stop.set()
        raise DeletionScopeError("simulated unsafe artifact")

    monkeypatch.setattr("inspection_platform.worker.service.purge_expired_jobs", fail_retention)
    settings = system_harness.settings.model_copy(update={"retention_scan_seconds": 0.01})
    worker = WorkerService(settings, worker_id="retention-worker")
    thread = Thread(target=worker.serve, args=(stop,))
    thread.start()
    thread.join(2)

    assert not thread.is_alive()
    assert calls == 2
