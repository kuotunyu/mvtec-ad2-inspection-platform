from __future__ import annotations

import math
from enum import StrEnum

from pydantic import field_validator

from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256


class InspectionDecision(StrEnum):
    """Human-review routing outcome derived from frozen model evidence."""

    PASS = "PASS"
    REVIEW = "REVIEW"


class PredictionRecord(ContractModel):
    """Model-owned, threshold-independent evidence for one input image."""

    input_id: str
    input_sha256: Sha256
    category: MVTecAD2Category
    anomaly_score: float
    anomaly_map_sha256: Sha256
    model_bundle_id: str
    input_path: str | None = None

    @field_validator("anomaly_score")
    @classmethod
    def require_finite_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("anomaly_score must be finite")
        return value
