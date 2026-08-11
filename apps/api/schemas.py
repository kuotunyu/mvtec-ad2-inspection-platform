from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from inspection_platform.contracts.dataset import MVTecAD2Category

JobStatus = Literal[
    "QUEUED", "RUNNING", "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED"
]


class CreateJobRequest(BaseModel):
    category: MVTecAD2Category
    image_count: int = Field(ge=1, le=2_000)


class JobResponse(BaseModel):
    id: str
    category: MVTecAD2Category
    image_count: int
    status: JobStatus = "QUEUED"
    created_at: datetime | None = None
    completed_count: int = 0
    error_count: int = 0


class ImageResponse(BaseModel):
    id: str
    filename: str
    source_url: str
    anomaly_map_url: str | None = None
    overlay_url: str | None = None
    anomaly_map_sha256: str | None = None
    overlay_sha256: str | None = None
    anomaly_score: float | None = None
    threshold: float | None = None
    model_outcome: Literal["PASS", "REVIEW"] | None = None
    human_decision: Literal["ACCEPT", "REJECT", "UNCERTAIN"] | None = None
    revision: int = 0
    error: str | None = None


class JobDetailResponse(JobResponse):
    images: list[ImageResponse]
    revision: int
    model_bundle_id: str | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class ReviewRequest(BaseModel):
    decision: Literal["ACCEPT", "REJECT", "UNCERTAIN"]
    note: str | None = Field(default=None, max_length=2_000)
    expected_revision: int = Field(ge=0)


class ReviewResponse(BaseModel):
    image_id: str
    decision: Literal["ACCEPT", "REJECT", "UNCERTAIN"]
    note: str | None
    revision: int
    created_at: datetime


class ReviewQueueResponse(BaseModel):
    items: list[ImageResponse]
    total: int


class SystemStatusResponse(BaseModel):
    backend_status: Literal["ready"]
    worker_status: Literal["current", "stale", "missing"]
    worker_heartbeat_at: datetime | None = None
    active_queue: int
    review_backlog: int
    image_errors: int


class ModelSummary(BaseModel):
    category: MVTecAD2Category
    family: str
    artifact_size_bytes: int
    gpu_p95_latency_ms: float
    peak_vram_mib: float
    image_auroc: float
    pixel_au_pro: float
    selection_reason: str


class ModelListResponse(BaseModel):
    items: list[ModelSummary]
    champion_matrix_sha256: str


class EvidenceResponse(BaseModel):
    public_gate_sha256: str
    dataset_manifest_sha256: str
    private_evaluation: str
    official_submission_performed: bool
    serving_benchmark_status: Literal["not evaluated", "passed"]
    serving_benchmark_sha256: str | None
    limitations: list[str]
    metric_definitions: dict[str, str]
    downloadable: dict[str, str]


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None
