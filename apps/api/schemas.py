from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from inspection_platform.contracts.dataset import MVTecAD2Category


class CreateJobRequest(BaseModel):
    category: MVTecAD2Category
    image_count: int = Field(ge=1, le=2_000)


class JobResponse(BaseModel):
    id: str
    category: MVTecAD2Category
    image_count: int
    status: Literal["QUEUED"] = "QUEUED"


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
