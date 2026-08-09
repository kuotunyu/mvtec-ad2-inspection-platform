from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from io import BytesIO
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
from inspection_platform.ingestion.images import ImageValidationError
from inspection_platform.ingestion.service import IngestionService, UploadStream
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
    ingestion = IngestionService(repositories, artifact_store)
    app = FastAPI(title="MVTec AD 2 Inspection API", version="1.0.0")
    app.state.sessions = sessions
    app.state.settings = configured
    registry = CollectorRegistry()
    jobs_total = Counter("inspection_jobs", "Created inspection jobs", registry=registry)

    def job_response(job: Job) -> JobResponse:
        return JobResponse(
            id=job.id,
            category=job.category,  # type: ignore[arg-type]
            image_count=job.image_count,
            status=_status(job.state),  # type: ignore[arg-type]
            created_at=job.created_at,
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
            human_decision=review.decision if review else None,  # type: ignore[arg-type]
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
        uploads: list[UploadStream] = []
        for item in files:
            uploads.append(
                UploadStream(Path(item.filename or "image").name, BytesIO(await item.read()))
            )
        try:
            result = ingestion.create_job(category, uploads)
        except (ImageValidationError, ValueError) as exc:
            return _error(request, 422, "invalid_upload", str(exc))
        with sessions() as session, session.begin():
            for upload, reference in zip(uploads, result.artifacts, strict=True):
                session.add(
                    InspectionImage(
                        id=str(uuid4()),
                        job_id=result.id,
                        artifact_key=reference.sha256,
                        filename=upload.filename,
                        media_type=reference.media_type,
                    )
                )
        jobs_total.inc()
        with sessions() as session:
            return job_response(session.get(Job, result.id))  # type: ignore[arg-type]

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
            base = job_response(job).model_dump()
            return JobDetailResponse(
                **base, images=output, revision=job.attempt, model_bundle_id=None
            )

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
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


app = create_app()
