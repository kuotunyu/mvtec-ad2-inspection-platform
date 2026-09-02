from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections.abc import Awaitable, Callable
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from shutil import disk_usage
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any, BinaryIO
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Counter, generate_latest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.models import (
    AuditEvent,
    InspectionImage,
    Job,
    Prediction,
    Review,
    WorkerHeartbeat,
)
from inspection_platform.db.repositories import Repositories
from inspection_platform.ingestion.images import (
    ImageValidationError,
    sanitize_filename,
    validate_image,
)
from inspection_platform.reports.builder import build_report_json
from inspection_platform.retention import DeletionScopeError, delete_job_artifacts
from inspection_platform.settings import Settings
from inspection_platform.storage.artifacts import ArtifactStore, artifact_store_lock

from .schemas import (
    CreateJobRequest,
    ErrorResponse,
    EvidenceResponse,
    ImageResponse,
    IngestionLimitsResponse,
    JobDetailResponse,
    JobListResponse,
    JobResponse,
    ModelListResponse,
    ModelSummary,
    ReviewQueueResponse,
    ReviewRequest,
    ReviewResponse,
    SystemStatusResponse,
)

_ROOT = Path(__file__).resolve().parents[2]
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


class _DuplicateJSONKey(ValueError):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/v1/jobs":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None:
            try:
                declared_bytes = int(declared)
            except ValueError:
                declared_bytes = self.max_bytes + 1
            if declared_bytes > self.max_bytes:
                await self._reject(scope, receive, send)
                return
        received = 0
        too_large = False

        async def bounded_receive() -> Message:
            nonlocal received, too_large
            if too_large:
                return {"type": "http.request", "body": b"", "more_body": False}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        response_messages: list[Message] = []

        async def capture_response(message: Message) -> None:
            response_messages.append(message)

        try:
            await self.app(scope, bounded_receive, capture_response)
        except Exception:
            if not too_large:
                raise
        if too_large:
            await self._reject(scope, receive, send)
            return
        for message in response_messages:
            await send(message)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        response = _error(
            request,
            413,
            "request_too_large",
            "Request body exceeds the configured total-size limit",
        )
        await response(scope, receive, send)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise _DuplicateJSONKey(key)
        output[key] = value
    return output


def _safe_csv_cell(value: str) -> str:
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id", "")
    return candidate if _REQUEST_ID.fullmatch(candidate) else str(uuid4())


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": _request_id(request)},
    )


def _status(value: str) -> str:
    normalized = value.upper()
    return "QUEUED" if normalized == "QUEUED" else normalized


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings()
    free_spool_bytes = disk_usage(configured.spool_root).free
    if free_spool_bytes < configured.minimum_spool_free_bytes:
        raise RuntimeError(
            "insufficient spool capacity: "
            f"requires at least {configured.minimum_spool_free_bytes} free bytes, "
            f"found {free_spool_bytes} at {configured.spool_root}"
        )
    sessions = create_engine_and_session(configured)
    repositories = Repositories(sessions)
    artifact_store = ArtifactStore(configured.artifact_root)
    app = FastAPI(title="MVTec AD 2 Inspection API", version="0.1.2")
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=configured.max_archive_uncompressed_bytes,
    )
    app.state.sessions = sessions
    app.state.settings = configured
    registry = CollectorRegistry()
    jobs_total = Counter("inspection_jobs", "Created inspection jobs", registry=registry)

    @app.middleware("http")
    async def reject_duplicate_json_keys(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if "application/json" in request.headers.get("content-type", ""):
            try:
                json.loads(await request.body(), object_pairs_hook=_unique_json_object)
            except _DuplicateJSONKey:
                return _error(request, 400, "duplicate_json_key", "JSON object keys must be unique")
            except json.JSONDecodeError:
                return _error(request, 400, "invalid_json", "Request body is not valid JSON")
        return await call_next(request)

    def job_response(job: Job, *, completed_count: int = 0, error_count: int = 0) -> JobResponse:
        return JobResponse(
            id=job.id,
            category=job.category,
            image_count=job.image_count,
            status=_status(job.state),
            created_at=job.created_at,
            completed_count=completed_count,
            error_count=error_count,
        )

    def image_response(
        image: InspectionImage, prediction: Prediction | None, review: Review | None
    ) -> ImageResponse:
        payload: dict[str, Any] = prediction.payload if prediction else {}
        return ImageResponse(
            id=image.id,
            filename=image.filename,
            source_url=f"/api/v1/artifacts/{image.id}/source",
            anomaly_map_url=payload.get("anomaly_map_url"),
            overlay_url=payload.get("overlay_url"),
            anomaly_map_sha256=payload.get("anomaly_map_sha256"),
            overlay_sha256=payload.get("overlay_sha256"),
            anomaly_score=payload.get("anomaly_score"),
            threshold=payload.get("threshold"),
            model_outcome=payload.get("model_outcome"),
            human_decision=review.decision if review else None,
            revision=review.revision if review else 0,
            error=payload.get("error"),
        )

    @app.get("/health/live", include_in_schema=False)
    @app.get("/api/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health/ready", response_model=None)
    def health_ready(request: Request) -> dict[str, str] | JSONResponse:
        try:
            with sessions() as session:
                session.scalar(select(func.count()).select_from(Job))
            configured.artifact_root.mkdir(parents=True, exist_ok=True)
        except (OSError, RuntimeError):
            return _error(request, 503, "service_not_ready", "Runtime storage is unavailable")
        return {"status": "ready"}

    @app.get("/api/v1/system/status", response_model=SystemStatusResponse)
    def system_status() -> SystemStatusResponse:
        with sessions() as session:
            latest = session.scalar(
                select(WorkerHeartbeat).order_by(WorkerHeartbeat.heartbeat_at.desc()).limit(1)
            )
            active = (
                session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.state.in_(("queued", "RUNNING")))
                )
                or 0
            )
            reviewed = set(session.scalars(select(Review.image_id)))
            predictions = list(session.scalars(select(Prediction)))
        if latest is None:
            worker_status = "missing"
        else:
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
                seconds=max(configured.heartbeat_seconds * 2, 5)
            )
            heartbeat_at = latest.heartbeat_at.replace(tzinfo=None)
            worker_status = "current" if heartbeat_at >= cutoff else "stale"
        return SystemStatusResponse(
            backend_status="ready",
            worker_status=worker_status,
            worker_heartbeat_at=latest.heartbeat_at if latest else None,
            active_queue=active,
            review_backlog=sum(
                prediction.payload.get("model_outcome") == "REVIEW"
                and prediction.image_id not in reviewed
                for prediction in predictions
            ),
            image_errors=sum(bool(prediction.payload.get("error")) for prediction in predictions),
            ingestion_limits=IngestionLimitsResponse(
                max_archive_files=configured.max_archive_files,
                max_upload_bytes=configured.max_upload_bytes,
            ),
        )

    @app.post("/api/jobs", status_code=201, response_model=JobResponse, include_in_schema=False)
    def create_legacy_job(body: CreateJobRequest) -> JobResponse:
        job = repositories.jobs.create(category=body.category, image_count=body.image_count)
        jobs_total.inc()
        return job_response(job)

    @app.get("/api/jobs/{job_id}", response_model=JobResponse, include_in_schema=False)
    def get_legacy_job(job_id: str, request: Request) -> JobResponse | JSONResponse:
        with sessions() as session:
            job = session.get(Job, job_id)
            return (
                job_response(job) if job else _error(request, 404, "job_not_found", "Job not found")
            )

    @app.post("/api/v1/jobs", status_code=201, response_model=JobResponse)
    async def create_job(
        request: Request,
        category: Annotated[str, Form()],
        files: Annotated[list[UploadFile], File()],
    ) -> JobResponse | JSONResponse:
        if category not in {
            "can",
            "fabric",
            "fruit_jelly",
            "rice",
            "sheet_metal",
            "vial",
            "wallplugs",
            "walnuts",
        }:
            return _error(request, 422, "invalid_category", "Unknown component category")
        if len(files) > configured.max_archive_files:
            return _error(
                request,
                413,
                "too_many_files",
                "Batch exceeds the configured file-count limit",
            )
        with ExitStack() as staged_uploads:
            accepted: list[tuple[str, BinaryIO | None, str, str, str | None]] = []
            for item in files:
                filename = sanitize_filename(item.filename or "image")
                content = await item.read(configured.max_upload_bytes + 1)
                await item.close()
                try:
                    image = validate_image(
                        BytesIO(content),
                        filename=filename,
                        max_bytes=configured.max_upload_bytes,
                        max_pixels=configured.max_image_pixels,
                    )
                    staged = staged_uploads.enter_context(
                        SpooledTemporaryFile(
                            max_size=64 * 1024,
                            mode="w+b",
                            dir=configured.spool_root,
                        )
                    )
                    staged.write(image.content)
                    staged.seek(0)
                    accepted.append((filename, staged, "", image.media_type, None))
                except ImageValidationError:
                    accepted.append(
                        (
                            filename,
                            None,
                            hashlib.sha256(content).hexdigest(),
                            "application/octet-stream",
                            "invalid_upload",
                        )
                    )
            created_at = datetime.now(UTC)
            job = Job(
                id=str(uuid4()),
                category=category,
                image_count=len(accepted),
                state="queued",
                created_at=created_at,
            )
            with (
                artifact_store_lock(configured.artifact_root),
                sessions() as session,
                session.begin(),
            ):
                session.add(job)
                session.add(
                    AuditEvent(
                        id=str(uuid4()),
                        action="job.created",
                        resource_id=job.id,
                        created_at=created_at,
                        dedupe_key=f"job.created:{job.id}",
                    )
                )
                session.flush()
                initial_predictions: list[Prediction] = []
                for filename, staged, artifact_key, media_type, error_code in accepted:
                    if staged is not None:
                        staged.seek(0)
                        artifact_key = artifact_store.put_stream(
                            staged, media_type=media_type
                        ).sha256
                    image_id = str(uuid4())
                    session.add(
                        InspectionImage(
                            id=image_id,
                            job_id=job.id,
                            artifact_key=artifact_key,
                            filename=filename,
                            media_type=media_type,
                        )
                    )
                    if error_code is not None:
                        initial_predictions.append(
                            Prediction(
                                id=str(uuid4()),
                                image_id=image_id,
                                payload={"error": error_code},
                            )
                        )
                session.flush()
                session.add_all(initial_predictions)
        jobs_total.inc()
        return job_response(job)

    @app.get("/api/v1/jobs", response_model=JobListResponse)
    def list_jobs(limit: int = 50, offset: int = 0) -> JobListResponse:
        bounded = min(max(limit, 1), 100)
        with sessions() as session:
            jobs = list(
                session.scalars(
                    select(Job)
                    .order_by(Job.created_at.desc())
                    .offset(max(offset, 0))
                    .limit(bounded)
                )
            )
            total = session.scalar(select(func.count()).select_from(Job)) or 0
            return JobListResponse(items=[job_response(job) for job in jobs], total=total)

    @app.get(
        "/api/v1/jobs/{job_id}",
        response_model=JobDetailResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_job(job_id: str, request: Request) -> JobDetailResponse | JSONResponse:
        with sessions() as session:
            job = session.get(Job, job_id)
            if job is None:
                return _error(request, 404, "job_not_found", "Job not found")
            images = list(
                session.scalars(select(InspectionImage).where(InspectionImage.job_id == job_id))
            )
            output: list[ImageResponse] = []
            for image in images:
                prediction = session.scalar(
                    select(Prediction).where(Prediction.image_id == image.id)
                )
                review = session.scalar(
                    select(Review)
                    .where(Review.image_id == image.id)
                    .order_by(Review.revision.desc())
                    .limit(1)
                )
                output.append(image_response(image, prediction, review))
            completed_count = sum(
                item.error is None and item.anomaly_score is not None for item in output
            )
            error_count = sum(item.error is not None for item in output)
            bundle_ids = {
                prediction.payload.get("model_bundle_id")
                for image in images
                if (
                    prediction := session.scalar(
                        select(Prediction).where(Prediction.image_id == image.id)
                    )
                )
                and prediction.payload.get("model_bundle_id")
            }
            base = job_response(
                job, completed_count=completed_count, error_count=error_count
            ).model_dump()
            return JobDetailResponse(
                **base,
                images=output,
                revision=job.attempt,
                model_bundle_id=next(iter(bundle_ids), None),
            )

    def report_response(job_id: str, request: Request, extension: str) -> Response:
        detail = get_job(job_id, request)
        if isinstance(detail, JSONResponse):
            return detail
        job_payload = detail.model_dump(mode="json")
        if extension == "json":
            body = build_report_json({"job": job_payload, "schema_version": "1.0.0"})
            media_type = "application/json"
        elif extension == "csv":
            stream = StringIO(newline="")
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["image_id", "filename", "model_outcome", "human_decision", "error"])
            for image in detail.images:
                writer.writerow(
                    [
                        image.id,
                        _safe_csv_cell(image.filename),
                        image.model_outcome or "",
                        image.human_decision or "",
                        image.error or "",
                    ]
                )
            body = stream.getvalue().encode("utf-8")
            media_type = "text/csv"
        else:
            rows = "".join(
                f"<tr><td>{html.escape(image.filename)}</td>"
                f"<td>{html.escape(image.model_outcome or '')}</td>"
                f"<td>{html.escape(image.human_decision or '')}</td>"
                f"<td>{html.escape(image.error or '')}</td></tr>"
                for image in detail.images
            )
            body = (
                "<!doctype html><meta charset=utf-8><title>Inspection report</title>"
                "<h1>Inspection evidence report</h1><table><thead><tr><th>File</th>"
                "<th>Model outcome</th><th>Human decision</th><th>Error</th></tr>"
                f"</thead><tbody>{rows}</tbody></table>"
            ).encode()
            media_type = "text/html"
        return Response(
            body,
            media_type=media_type,
            headers={
                "content-disposition": f'attachment; filename="inspection-{job_id}.{extension}"',
                "x-content-sha256": hashlib.sha256(body).hexdigest(),
            },
        )

    @app.get("/api/v1/jobs/{job_id}/report.json", response_model=None)
    def report_json(job_id: str, request: Request) -> Response:
        return report_response(job_id, request, "json")

    @app.get("/api/v1/jobs/{job_id}/report.csv", response_model=None)
    def report_csv(job_id: str, request: Request) -> Response:
        return report_response(job_id, request, "csv")

    @app.get("/api/v1/jobs/{job_id}/report.html", response_model=None)
    def report_html(job_id: str, request: Request) -> Response:
        return report_response(job_id, request, "html")

    @app.delete("/api/v1/jobs/{job_id}/artifacts", response_model=None)
    def delete_artifacts(job_id: str, request: Request) -> dict[str, int] | JSONResponse:
        with sessions() as session:
            job = session.get(Job, job_id)
            if job is None:
                return _error(request, 404, "job_not_found", "Job not found")
            if _status(job.state) not in {
                "COMPLETED",
                "COMPLETED_WITH_ERRORS",
                "FAILED",
                "CANCELLED",
            }:
                return _error(
                    request,
                    409,
                    "job_not_terminal",
                    "Artifacts can only be deleted after the job is terminal",
                )
        try:
            result = delete_job_artifacts(configured.artifact_root, sessions, job_id)
        except (DeletionScopeError, OSError):
            return _error(
                request, 409, "deletion_scope_invalid", "Artifact deletion could not be verified"
            )
        return {"deleted_files": result.deleted_files}

    @app.post(
        "/api/v1/jobs/{job_id}/cancel",
        response_model=JobResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def cancel_job(job_id: str, request: Request) -> JobResponse | JSONResponse:
        with sessions() as session, session.begin():
            job = session.get(Job, job_id)
            if job is None:
                return _error(request, 404, "job_not_found", "Job not found")
            if _status(job.state) not in {"QUEUED", "RUNNING"}:
                return _error(request, 409, "job_not_cancellable", "Job is already terminal")
            job.state = "CANCELLED"
            session.flush()
            return job_response(job)

    @app.get("/api/v1/artifacts/{image_id}/source", response_model=None)
    def source_artifact(image_id: str, request: Request) -> FileResponse | JSONResponse:
        with sessions() as session:
            image = session.get(InspectionImage, image_id)
            if image is None:
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            deleted = session.scalar(
                select(AuditEvent.id)
                .where(
                    AuditEvent.resource_id == image.job_id,
                    AuditEvent.action == "job.artifacts_deleted",
                )
                .limit(1)
            )
            if deleted is not None:
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            path = (
                configured.artifact_root / image.artifact_key[:2] / image.artifact_key
            ).resolve()
            try:
                path.relative_to(configured.artifact_root.resolve())
            except ValueError:
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            if not path.is_file():
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            return FileResponse(path, media_type=image.media_type, filename=image.filename)

    def prediction_artifact(
        image_id: str, request: Request, *, payload_key: str
    ) -> FileResponse | JSONResponse:
        with sessions() as session:
            prediction = session.scalar(select(Prediction).where(Prediction.image_id == image_id))
            image = session.get(InspectionImage, image_id)
            deleted = (
                session.scalar(
                    select(AuditEvent.id)
                    .where(
                        AuditEvent.resource_id == image.job_id,
                        AuditEvent.action == "job.artifacts_deleted",
                    )
                    .limit(1)
                )
                if image is not None
                else None
            )
            if image is None or deleted is not None:
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            artifact_key = prediction.payload.get(payload_key) if prediction else None
            if not isinstance(artifact_key, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_key):
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            path = (configured.artifact_root / artifact_key[:2] / artifact_key).resolve()
            try:
                path.relative_to(configured.artifact_root.resolve())
            except ValueError:
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            if not path.is_file():
                return _error(request, 404, "artifact_not_found", "Artifact not found")
            return FileResponse(path, media_type="image/png")

    @app.get("/api/v1/artifacts/{image_id}/anomaly-map", response_model=None)
    def anomaly_map_artifact(image_id: str, request: Request) -> FileResponse | JSONResponse:
        return prediction_artifact(image_id, request, payload_key="anomaly_map_artifact_key")

    @app.get("/api/v1/artifacts/{image_id}/overlay", response_model=None)
    def overlay_artifact(image_id: str, request: Request) -> FileResponse | JSONResponse:
        return prediction_artifact(image_id, request, payload_key="overlay_artifact_key")

    @app.get("/api/v1/reviews", response_model=ReviewQueueResponse)
    def review_queue() -> ReviewQueueResponse:
        with sessions() as session:
            pending = (
                Prediction.payload["model_outcome"].as_string() == "REVIEW",
                ~select(Review.id).where(Review.image_id == InspectionImage.id).exists(),
            )
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(InspectionImage)
                    .join(Prediction, Prediction.image_id == InspectionImage.id)
                    .where(*pending)
                )
                or 0
            )
            rows = session.execute(
                select(InspectionImage, Prediction)
                .join(Prediction, Prediction.image_id == InspectionImage.id)
                .where(*pending)
                .order_by(InspectionImage.id)
                .limit(100)
            )
            items = [image_response(image, prediction, None) for image, prediction in rows]
            return ReviewQueueResponse(items=items, total=total)

    @app.post(
        "/api/v1/reviews/{image_id}",
        status_code=201,
        response_model=ReviewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def record_review(
        image_id: str, body: ReviewRequest, request: Request
    ) -> ReviewResponse | JSONResponse:
        try:
            with sessions() as session, session.begin():
                if session.get(InspectionImage, image_id) is None:
                    return _error(request, 404, "image_not_found", "Inspection image not found")
                current = session.scalar(
                    select(Review)
                    .where(Review.image_id == image_id)
                    .order_by(Review.revision.desc())
                    .limit(1)
                )
                revision = current.revision if current else 0
                if revision != body.expected_revision:
                    return _error(
                        request,
                        409,
                        "review_revision_conflict",
                        "This item was reviewed elsewhere",
                    )
                record = Review(
                    id=str(uuid4()),
                    image_id=image_id,
                    decision=body.decision,
                    note=body.note,
                    created_at=datetime.now(UTC),
                    revision=revision + 1,
                )
                session.add(record)
                session.flush()
                session.add(
                    AuditEvent(
                        id=str(uuid4()),
                        action="review.recorded",
                        resource_id=image_id,
                        created_at=record.created_at,
                        dedupe_key=f"review.recorded:{image_id}:{record.revision}",
                    )
                )
                return ReviewResponse(
                    image_id=image_id,
                    decision=body.decision,
                    note=body.note,
                    revision=record.revision,
                    created_at=record.created_at,
                )
        except IntegrityError:
            return _error(
                request, 409, "review_revision_conflict", "This item was reviewed elsewhere"
            )

    @app.get("/api/v1/models", response_model=ModelListResponse)
    def models() -> ModelListResponse:
        payload = json.loads((_ROOT / "reports/champions.json").read_text(encoding="utf-8"))
        items: list[ModelSummary] = []
        for decision in payload["decisions"]:
            winner = decision["decision"]["winner"]
            candidate = next(item for item in decision["candidates"] if item["family"] == winner)
            items.append(
                ModelSummary(
                    category=decision["category"],
                    family=winner,
                    artifact_size_bytes=candidate["artifact_size_bytes"],
                    gpu_p95_latency_ms=candidate["gpu_p95_latency_ms"],
                    peak_vram_mib=candidate["peak_vram_mib"],
                    image_auroc=candidate["image_auroc"],
                    pixel_au_pro=candidate["au_pro"],
                    selection_reason=decision["decision"]["reason"],
                )
            )
        return ModelListResponse(items=items, champion_matrix_sha256=payload["canonical_sha256"])

    @app.get("/api/v1/evidence", response_model=EvidenceResponse)
    def evidence() -> EvidenceResponse:
        benchmark = json.loads(
            (_ROOT / "reports/public_benchmark.json").read_text(encoding="utf-8")
        )
        serving_path = _ROOT / "docs/assets/evidence/serving-benchmark.json"
        official_path = _ROOT / "docs/assets/evidence/official-private-result.json"
        serving_status = "not evaluated"
        serving_sha256 = None
        downloadable = {
            "champions": "/evidence/champions.json",
            "public_benchmark": "/evidence/public-benchmark.json",
        }
        if serving_path.is_file():
            serving = json.loads(serving_path.read_text(encoding="utf-8"))
            if serving.get("status") != "passed":
                raise ValueError("committed serving benchmark is not a passing artifact")
            serving_status = "passed"
            serving_sha256 = hashlib.sha256(serving_path.read_bytes()).hexdigest()
            downloadable["serving_benchmark"] = "/evidence/serving-benchmark.json"
        if not official_path.is_file():
            raise ValueError("committed official private evidence is missing")
        official = json.loads(official_path.read_text(encoding="utf-8"))
        if official.get("status") != "DONE" or official.get("verdict") != "PRIVATE-NO-GO":
            raise ValueError("committed official private evidence is not a no-go result")
        downloadable["official_private_result"] = "/evidence/official-private-result.json"
        return EvidenceResponse(
            public_gate_sha256=benchmark["canonical_sha256"],
            dataset_manifest_sha256=benchmark["dataset_manifest_sha256"],
            private_evaluation="NO-GO under lighting shift",
            official_submission_performed=True,
            serving_benchmark_status=serving_status,
            serving_benchmark_sha256=serving_sha256,
            limitations=[
                "MVTec AD 2 is licensed for non-commercial research use and is not redistributed.",
                "Model outcomes are PASS or REVIEW; a human owns final disposition.",
                "The system detects anomalous evidence but does not classify defect type "
                "or root cause.",
                "Latency measurements are specific to the recorded local hardware and "
                "software stack.",
                "The official frozen private gate is PRIVATE-NO-GO; no retuning or second "
                "submission was performed.",
                "The submitted archive had no thresholded PNGs, so official ClassF1 and "
                "SegF1 are zero and are not treated as measured thresholded-map performance.",
            ],
            metric_definitions={
                "image_auroc": "Image AUROC (higher is better)",
                "pixel_au_pro": "Pixel AU-PRO (FPR ≤ 0.30, higher is better)",
            },
            downloadable=downloadable,
        )

    @app.get("/evidence/champions.json")
    def champions_download() -> FileResponse:
        return FileResponse(_ROOT / "reports/champions.json", media_type="application/json")

    @app.get("/evidence/public-benchmark.json")
    def benchmark_download() -> FileResponse:
        return FileResponse(_ROOT / "reports/public_benchmark.json", media_type="application/json")

    @app.get("/evidence/serving-benchmark.json", response_model=None)
    def serving_benchmark_download(request: Request) -> FileResponse | JSONResponse:
        path = _ROOT / "docs/assets/evidence/serving-benchmark.json"
        if not path.is_file():
            return _error(request, 404, "evidence_not_found", "Evidence artifact not found")
        return FileResponse(path, media_type="application/json")

    @app.get("/evidence/official-private-result.json", response_model=None)
    def official_private_result_download(request: Request) -> FileResponse | JSONResponse:
        path = _ROOT / "docs/assets/evidence/official-private-result.json"
        if not path.is_file():
            return _error(request, 404, "evidence_not_found", "Evidence artifact not found")
        return FileResponse(path, media_type="application/json")

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")

    web_dist = _ROOT / "apps" / "web" / "dist"
    if web_dist.is_dir():

        @app.get("/inspect", include_in_schema=False)
        @app.get("/review", include_in_schema=False)
        @app.get("/evidence", include_in_schema=False)
        @app.get("/jobs/{web_job_id}", include_in_schema=False)
        def web_route(web_job_id: str | None = None) -> FileResponse:
            del web_job_id
            return FileResponse(web_dist / "index.html", media_type="text/html")

        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app
