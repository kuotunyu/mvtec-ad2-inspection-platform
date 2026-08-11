from __future__ import annotations

import logging
import signal
import socket
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.models import AuditEvent, InspectionImage, Job, Prediction
from inspection_platform.inference.evidence import SpatialEvidence, render_spatial_evidence
from inspection_platform.inference.runtime import InferenceRuntime
from inspection_platform.jobs.leases import claim_next_job, recover_expired_leases, renew_lease
from inspection_platform.registry.repository import BundleIntegrityError, ModelRegistry
from inspection_platform.retention import DeletionScopeError, purge_expired_jobs
from inspection_platform.settings import Settings
from inspection_platform.storage.artifacts import ArtifactStore, artifact_store_lock
from inspection_platform.worker.heartbeat import (
    LeaseHeartbeat,
    LeaseLostError,
    record_worker_heartbeat,
)

LOGGER = logging.getLogger("inspection.worker")


class WorkerService:
    def __init__(self, settings: Settings, *, worker_id: str | None = None) -> None:
        self.settings = settings
        self.sessions = create_engine_and_session(settings)
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid4()}"
        self.artifacts = ArtifactStore(settings.artifact_root)

    def process_once(self) -> bool:
        record_worker_heartbeat(self.sessions, self.worker_id, status="idle")
        recover_expired_leases(self.sessions, datetime.now(UTC))
        job = claim_next_job(
            self.sessions,
            self.worker_id,
            datetime.now(UTC),
            lease_seconds=self.settings.lease_seconds,
        )
        if job is None:
            return False
        record_worker_heartbeat(self.sessions, self.worker_id, status="busy")
        try:
            with LeaseHeartbeat(
                lambda: self._renew_job_lease(job.id, job.attempt),
                interval_seconds=self.settings.heartbeat_seconds,
            ) as lease:
                failures = self._process_claimed_job(job, lease)
            LOGGER.info("job completed", extra={"job_id": job.id, "failures": failures})
        except LeaseLostError:
            LOGGER.warning("job lease lost", extra={"job_id": job.id})
            return True
        except Exception as exc:
            self._fail_owned_job(job, exc)
            return True
        finally:
            record_worker_heartbeat(self.sessions, self.worker_id, status="idle")
        return True

    def _renew_job_lease(self, job_id: str, attempt: int) -> bool:
        owned = renew_lease(
            self.sessions,
            job_id,
            self.worker_id,
            datetime.now(UTC),
            lease_seconds=self.settings.lease_seconds,
            expected_attempt=attempt,
        )
        record_worker_heartbeat(self.sessions, self.worker_id, status="busy")
        return owned

    def _process_claimed_job(self, job: Job, lease: LeaseHeartbeat) -> int:
        failures = 0
        manifest_path = (
            self.settings.model_registry_root / "categories" / job.category / "manifest.json"
        )
        manifest = ModelRegistry(self.settings.model_registry_root).register(manifest_path)
        runtime = InferenceRuntime.load(
            manifest,
            self.settings.model_registry_root,
            device=self.settings.inference_device,
            trust_verified_bundle=True,
        )
        with self.sessions() as session:
            images = list(
                session.scalars(
                    select(InspectionImage)
                    .where(InspectionImage.job_id == job.id)
                    .order_by(InspectionImage.id)
                )
            )
        for image in images:
            lease.assert_owned()
            with self.sessions() as session:
                existing = session.scalar(select(Prediction).where(Prediction.image_id == image.id))
            if existing is not None:
                if existing.payload.get("error"):
                    failures += 1
                continue
            manifest_path = (
                self.settings.artifact_root / image.artifact_key[:2] / image.artifact_key
            )
            evidence = None
            try:
                image_bytes = manifest_path.read_bytes()
                detailed = runtime.predict_with_map(image_bytes, input_id=image.id)
                evidence = render_spatial_evidence(image_bytes, detailed.anomaly_map)
                prediction = detailed.record
                threshold = manifest.threshold if manifest.threshold is not None else 0.5
                payload = {
                    "anomaly_map_raw_sha256": prediction.anomaly_map_sha256,
                    "anomaly_map_sha256": evidence.anomaly_map_sha256,
                    "anomaly_map_url": f"/api/v1/artifacts/{image.id}/anomaly-map",
                    "anomaly_score": prediction.anomaly_score,
                    "model_bundle_id": prediction.model_bundle_id,
                    "model_outcome": "REVIEW" if prediction.anomaly_score >= threshold else "PASS",
                    "overlay_sha256": evidence.overlay_sha256,
                    "overlay_url": f"/api/v1/artifacts/{image.id}/overlay",
                    "threshold": threshold,
                }
            except Exception:
                failures += 1
                payload = {"error": "inference_failed"}
            lease.assert_owned()
            self._publish_prediction(job, image.id, payload, evidence)
        lease.assert_owned()
        with self.sessions() as session, session.begin():
            completed = cast(
                CursorResult[Any],
                session.execute(
                    update(Job)
                    .where(
                        Job.id == job.id,
                        Job.state == "RUNNING",
                        Job.worker_id == self.worker_id,
                        Job.attempt == job.attempt,
                        Job.lease_expires_at > datetime.now(UTC),
                    )
                    .values(
                        state="COMPLETED_WITH_ERRORS" if failures else "COMPLETED",
                        worker_id=None,
                        heartbeat_at=None,
                        lease_expires_at=None,
                    )
                ),
            )
            if completed.rowcount != 1:
                raise LeaseLostError("worker no longer owns job completion")
            session.execute(
                sqlite_insert(AuditEvent)
                .values(
                    id=str(uuid4()),
                    action="job.completed",
                    resource_id=job.id,
                    created_at=datetime.now(UTC),
                    dedupe_key=f"job.completed:{job.id}",
                )
                .on_conflict_do_nothing(index_elements=[AuditEvent.dedupe_key])
            )
        return failures

    def _publish_prediction(
        self,
        job: Job,
        image_id: str,
        payload: dict[str, Any],
        evidence: SpatialEvidence | None,
    ) -> None:
        with (
            artifact_store_lock(self.settings.artifact_root),
            self.sessions() as session,
            session.begin(),
        ):
            self._fence_owned_job(session, job)
            if evidence is not None:
                anomaly_ref = self.artifacts.put_stream(
                    BytesIO(evidence.anomaly_map_png), media_type="image/png"
                )
                overlay_ref = self.artifacts.put_stream(
                    BytesIO(evidence.overlay_png), media_type="image/png"
                )
                payload["anomaly_map_artifact_key"] = anomaly_ref.sha256
                payload["overlay_artifact_key"] = overlay_ref.sha256
            session.execute(
                sqlite_insert(Prediction)
                .values(id=str(uuid4()), image_id=image_id, payload=payload)
                .on_conflict_do_nothing(index_elements=[Prediction.image_id])
            )

    def _fence_owned_job(self, session: Session, job: Job) -> None:
        fenced = cast(
            CursorResult[Any],
            session.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.state == "RUNNING",
                    Job.worker_id == self.worker_id,
                    Job.attempt == job.attempt,
                    Job.lease_expires_at > datetime.now(UTC),
                )
                .values(worker_id=self.worker_id)
            ),
        )
        if fenced.rowcount != 1:
            raise LeaseLostError("worker no longer owns prediction publication")

    def _fail_owned_job(self, job: Job, exc: Exception) -> None:
        error_code = (
            "bundle_integrity_failed"
            if isinstance(exc, (BundleIntegrityError, OSError))
            else "worker_failed"
        )
        LOGGER.error("job failed", extra={"job_id": job.id, "error_code": error_code})
        with self.sessions() as session, session.begin():
            failed = cast(
                CursorResult[Any],
                session.execute(
                    update(Job)
                    .where(
                        Job.id == job.id,
                        Job.state == "RUNNING",
                        Job.worker_id == self.worker_id,
                        Job.attempt == job.attempt,
                        Job.lease_expires_at > datetime.now(UTC),
                    )
                    .values(
                        state="FAILED",
                        worker_id=None,
                        heartbeat_at=None,
                        lease_expires_at=None,
                    )
                ),
            )
            if failed.rowcount != 1:
                return
            images = list(
                session.scalars(select(InspectionImage).where(InspectionImage.job_id == job.id))
            )
            for image in images:
                session.execute(
                    sqlite_insert(Prediction)
                    .values(
                        id=str(uuid4()),
                        image_id=image.id,
                        payload={"error": error_code},
                    )
                    .on_conflict_do_nothing(index_elements=[Prediction.image_id])
                )

    def serve(self, stop: Event) -> None:
        ready = Path("/tmp/inspection-worker.ready")
        ready.write_text(self.worker_id, encoding="utf-8")
        LOGGER.info("worker heartbeat", extra={"worker_id": self.worker_id})
        next_retention_scan = monotonic()
        while not stop.is_set():
            worked = self.process_once()
            if monotonic() >= next_retention_scan:
                try:
                    result = purge_expired_jobs(
                        self.settings.artifact_root,
                        self.sessions,
                        datetime.now(UTC) - timedelta(days=self.settings.retention_days),
                    )
                    if result.deleted_jobs or result.failed_jobs:
                        LOGGER.info(
                            "retention completed",
                            extra={
                                "deleted_jobs": result.deleted_jobs,
                                "deleted_files": result.deleted_files,
                                "failed_jobs": result.failed_jobs,
                                "failed_job_ids": result.failed_job_ids,
                            },
                        )
                except (DeletionScopeError, OSError, SQLAlchemyError):
                    LOGGER.exception("retention scan failed; worker will retry later")
                finally:
                    next_retention_scan = monotonic() + self.settings.retention_scan_seconds
            stop.wait(0.1 if worked else 1.0)


def serve(settings: Settings | None = None) -> None:
    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    WorkerService(settings or Settings()).serve(stop)


__all__ = ["WorkerService", "serve"]
