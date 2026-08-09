from __future__ import annotations

import logging
import signal
import socket
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from uuid import uuid4

from sqlalchemy import select

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.models import AuditEvent, InspectionImage, Job, Prediction
from inspection_platform.inference.runtime import InferenceRuntime
from inspection_platform.jobs.leases import claim_next_job, recover_expired_leases
from inspection_platform.registry.repository import BundleIntegrityError, ModelRegistry
from inspection_platform.settings import Settings

LOGGER = logging.getLogger("inspection.worker")


class WorkerService:
    def __init__(self, settings: Settings, *, worker_id: str | None = None) -> None:
        self.settings = settings
        self.sessions = create_engine_and_session(settings)
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid4()}"

    def process_once(self) -> bool:
        recover_expired_leases(self.sessions, datetime.now(UTC))
        job = claim_next_job(self.sessions, self.worker_id, datetime.now(UTC))
        if job is None:
            return False
        failures = 0
        try:
            manifest_path = (
                self.settings.model_registry_root / "categories" / job.category / "manifest.json"
            )
            manifest = ModelRegistry(self.settings.model_registry_root).register(manifest_path)
            runtime = InferenceRuntime.load(manifest)
            with self.sessions() as session:
                images = list(
                    session.scalars(
                        select(InspectionImage)
                        .where(InspectionImage.job_id == job.id)
                        .order_by(InspectionImage.id)
                    )
                )
            for image in images:
                with self.sessions() as session:
                    existing = session.scalar(
                        select(Prediction).where(Prediction.image_id == image.id)
                    )
                if existing is not None:
                    if existing.payload.get("error"):
                        failures += 1
                    continue
                try:
                    artifact = (
                        self.settings.artifact_root / image.artifact_key[:2] / image.artifact_key
                    )
                    prediction = runtime.predict(artifact.read_bytes(), input_id=image.id)
                    threshold = manifest.threshold if manifest.threshold is not None else 0.5
                    source_url = f"/api/v1/artifacts/{image.id}/source"
                    payload = {
                        "anomaly_map_url": source_url,
                        "anomaly_map_sha256": prediction.anomaly_map_sha256,
                        "anomaly_score": prediction.anomaly_score,
                        "model_bundle_id": prediction.model_bundle_id,
                        "model_outcome": (
                            "REVIEW" if prediction.anomaly_score >= threshold else "PASS"
                        ),
                        "overlay_url": source_url,
                        "threshold": threshold,
                    }
                except Exception:
                    failures += 1
                    payload = {"error": "inference_failed"}
                with self.sessions() as session, session.begin():
                    if (
                        session.scalar(select(Prediction).where(Prediction.image_id == image.id))
                        is None
                    ):
                        session.add(Prediction(id=str(uuid4()), image_id=image.id, payload=payload))
            with self.sessions() as session, session.begin():
                current = session.get(Job, job.id)
                if current is not None and current.state == "RUNNING":
                    current.state = "COMPLETED_WITH_ERRORS" if failures else "COMPLETED"
                    current.worker_id = None
                    current.heartbeat_at = None
                    current.lease_expires_at = None
                    completed_audit = session.scalar(
                        select(AuditEvent).where(
                            AuditEvent.resource_id == job.id,
                            AuditEvent.action == "job.completed",
                        )
                    )
                    if completed_audit is None:
                        session.add(
                            AuditEvent(
                                id=str(uuid4()),
                                action="job.completed",
                                resource_id=job.id,
                                created_at=datetime.now(UTC),
                            )
                        )
            LOGGER.info("job completed", extra={"job_id": job.id, "failures": failures})
        except Exception as exc:
            error_code = (
                "bundle_integrity_failed"
                if isinstance(exc, (BundleIntegrityError, OSError))
                else "worker_failed"
            )
            LOGGER.error("job failed", extra={"job_id": job.id, "error_code": error_code})
            with self.sessions() as session, session.begin():
                current = session.get(Job, job.id)
                if current is not None and current.state == "RUNNING":
                    current.state = "FAILED"
                    current.worker_id = None
                    current.heartbeat_at = None
                    current.lease_expires_at = None
                images = list(
                    session.scalars(select(InspectionImage).where(InspectionImage.job_id == job.id))
                )
                for image in images:
                    if (
                        session.scalar(select(Prediction).where(Prediction.image_id == image.id))
                        is None
                    ):
                        session.add(
                            Prediction(
                                id=str(uuid4()),
                                image_id=image.id,
                                payload={"error": error_code},
                            )
                        )
            return True
        return True

    def serve(self, stop: Event) -> None:
        ready = Path("/tmp/inspection-worker.ready")
        ready.write_text(self.worker_id, encoding="utf-8")
        LOGGER.info("worker heartbeat", extra={"worker_id": self.worker_id})
        while not stop.is_set():
            worked = self.process_once()
            stop.wait(0.1 if worked else 1.0)


def serve(settings: Settings | None = None) -> None:
    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    WorkerService(settings or Settings()).serve(stop)


__all__ = ["WorkerService", "serve"]
