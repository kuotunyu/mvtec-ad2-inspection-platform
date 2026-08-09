from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CollectorRegistry, Counter, generate_latest

from .schemas import CreateJobRequest, ErrorResponse, JobResponse


def create_app() -> FastAPI:
    app = FastAPI(title="MVTec AD 2 Inspection API", version="1.0.0")
    jobs: dict[str, JobResponse] = {}
    registry = CollectorRegistry()
    jobs_total = Counter("inspection_jobs", "Created inspection jobs", registry=registry)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/jobs", status_code=201, response_model=JobResponse)
    def create_job(request: CreateJobRequest) -> JobResponse:
        job = JobResponse(id=str(uuid4()), **request.model_dump())
        jobs[job.id] = job
        jobs_total.inc()
        return job

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")

    @app.get(
        "/api/jobs/{job_id}",
        response_model=JobResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_job(job_id: str, request: Request) -> JobResponse | JSONResponse:
        job = jobs.get(job_id)
        if job is not None:
            return job
        request_id = request.headers.get("x-request-id") or str(uuid4())
        return JSONResponse(
            status_code=404,
            content={
                "code": "job_not_found",
                "message": "Job not found",
                "request_id": request_id,
            },
        )

    return app


app = create_app()
