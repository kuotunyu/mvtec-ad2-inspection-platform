from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Counter, generate_latest
from sqlalchemy import func, select

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.models import InspectionImage, Job, Prediction, Review
from inspection_platform.db.repositories import Repositories
from inspection_platform.ingestion.images import (
    ImageValidationError,
    sanitize_filename,
    validate_image,
)
from inspection_platform.reports.builder import build_report_json
from inspection_platform.retention import DeletionScopeError, delete_job_artifacts
from inspection_platform.settings import Settings
from inspection_platform.storage.artifacts import ArtifactStore

from .schemas import (
    CreateJobRequest,
    ErrorResponse,
    EvidenceResponse,
    ImageResponse,
    JobDetailResponse,
    JobListResponse,
    JobResponse,
    ModelListResponse,
    ModelSummary,
    ReviewQueueResponse,
    ReviewRequest,
    ReviewResponse,
)

_ROOT = Path(__file__).resolve().parents[2]
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


class _DuplicateJSONKey(ValueError):
    pass


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
    sessions = create_engine_and_session(configured)
    repositories = Repositories(sessions)
    artifact_store = ArtifactStore(configured.artifact_root)
    app = FastAPI(title="MVTec AD 2 Inspection API", version="1.0.0")
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
        accepted: list[tuple[str, str, str, str | None]] = []
        for item in files:
            filename = sanitize_filename(item.filename or "image")
            content = await item.read()
            try:
                image = validate_image(
                    BytesIO(content),
                    filename=filename,
                    max_bytes=configured.max_upload_bytes,
                    max_pixels=configured.max_image_pixels,
                )
                reference = artifact_store.put_stream(
                    BytesIO(image.content), media_type=image.media_type
                )
                accepted.append((filename, reference.sha256, reference.media_type, None))
            except ImageValidationError:
                accepted.append(
                    (
                        filename,
                        hashlib.sha256(content).hexdigest(),
                        "application/octet-stream",
                        "invalid_upload",
                    )
                )
        job = repositories.jobs.create(category=category, image_count=len(accepted))
        with sessions() as session, session.begin():
            for filename, artifact_key, media_type, error_code in accepted:
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
                    session.add(
                        Prediction(
                            id=str(uuid4()), image_id=image_id, payload={"error": error_code}
                        )
                    )
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
            if session.get(Job, job_id) is None:
                return _error(request, 404, "job_not_found", "Job not found")
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

    @app.get("/api/v1/reviews", response_model=ReviewQueueResponse)
    def review_queue() -> ReviewQueueResponse:
        with sessions() as session:
            images = list(
                session.scalars(select(InspectionImage).order_by(InspectionImage.id).limit(100))
            )
            items: list[ImageResponse] = []
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
                if (
                    prediction
                    and prediction.payload.get("model_outcome") == "REVIEW"
                    and review is None
                ):
                    items.append(image_response(image, prediction, None))
            return ReviewQueueResponse(items=items, total=len(items))

    @app.post(
        "/api/v1/reviews/{image_id}",
        status_code=201,
        response_model=ReviewResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def record_review(
        image_id: str, body: ReviewRequest, request: Request
    ) -> ReviewResponse | JSONResponse:
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
                    request, 409, "review_revision_conflict", "This item was reviewed elsewhere"
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
            return ReviewResponse(
                image_id=image_id,
                decision=body.decision,
                note=body.note,
                revision=record.revision,
                created_at=record.created_at,
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
        return EvidenceResponse(
            public_gate_sha256=benchmark["canonical_sha256"],
            dataset_manifest_sha256=benchmark["dataset_manifest_sha256"],
            private_evaluation="not submitted",
            official_submission_performed=False,
            limitations=[
                "MVTec AD 2 is licensed for non-commercial research use and is not redistributed.",
                "Model outcomes are PASS or REVIEW; a human owns final disposition.",
                "The system detects anomalous evidence but does not classify defect type "
                "or root cause.",
                "Latency measurements are specific to the recorded local hardware and "
                "software stack.",
            ],
            metric_definitions={
                "image_auroc": "Image AUROC (higher is better)",
                "pixel_au_pro": "Pixel AU-PRO (FPR ≤ 0.30, higher is better)",
            },
            downloadable={
                "champions": "/evidence/champions.json",
                "public_benchmark": "/evidence/public-benchmark.json",
            },
        )

    @app.get("/evidence/champions.json")
    def champions_download() -> FileResponse:
        return FileResponse(_ROOT / "reports/champions.json", media_type="application/json")

    @app.get("/evidence/public-benchmark.json")
    def benchmark_download() -> FileResponse:
        return FileResponse(_ROOT / "reports/public_benchmark.json", media_type="application/json")

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
