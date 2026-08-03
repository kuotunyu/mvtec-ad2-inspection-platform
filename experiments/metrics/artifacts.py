from __future__ import annotations

from typing import Annotated, Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category

METRIC_CONTRACT_VERSION: Final[Literal["1.0.0"]] = "1.0.0"
CONFORMAL_QUANTILE_RULE: Final[Literal["k = min(n, ceil((n + 1) * (1 - alpha)))"]] = (
    "k = min(n, ceil((n + 1) * (1 - alpha)))"
)
DISTRIBUTION_SHIFT_WARNING: Final[
    Literal["Validation coverage is not guaranteed under distribution shift."]
] = "Validation coverage is not guaranteed under distribution shift."


class ThresholdResult(ContractModel):
    """Frozen validation-only conformal upper threshold evidence."""

    metric_contract_version: Literal["1.0.0"] = METRIC_CONTRACT_VERSION
    calibration_split: Literal["validation/good"] = "validation/good"
    quantile_rule: Literal["k = min(n, ceil((n + 1) * (1 - alpha)))"] = CONFORMAL_QUANTILE_RULE
    distribution_shift_warning: Literal[
        "Validation coverage is not guaranteed under distribution shift."
    ] = DISTRIBUTION_SHIFT_WARNING
    alpha: Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)]
    rank: Annotated[int, Field(gt=0)]
    n: Annotated[int, Field(gt=0)]
    threshold: Annotated[float, Field(allow_inf_nan=False)]
    achieved_validation_review_rate: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def require_valid_rank(self) -> Self:
        if self.rank > self.n:
            raise ValueError("rank must not exceed calibration sample count")
        return self


MetricValue = Annotated[float | None, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class ImageMetrics(ContractModel):
    """Image-level discrimination metrics and their class support."""

    metric_contract_version: Literal["1.0.0"] = METRIC_CONTRACT_VERSION
    auroc: MetricValue
    average_precision: MetricValue
    normal_count: Annotated[int, Field(ge=0)]
    anomaly_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def require_metric_support_consistency(self) -> Self:
        if self.normal_count + self.anomaly_count == 0:
            raise ValueError("image metric support must not be empty")
        has_both_classes = self.normal_count > 0 and self.anomaly_count > 0
        metrics_defined = self.auroc is not None and self.average_precision is not None
        if metrics_defined != has_both_classes:
            raise ValueError("image metrics must be defined when both classes are present")
        return self


class PixelMetrics(ContractModel):
    """Pixel discrimination and region-overlap metrics through frozen FPR 0.30."""

    metric_contract_version: Literal["1.0.0"] = METRIC_CONTRACT_VERSION
    auroc: MetricValue
    average_precision: MetricValue
    au_pro: MetricValue
    pro_fpr_limit: Annotated[float, Field(gt=0.0, le=1.0, allow_inf_nan=False)] = 0.3
    normal_pixel_count: Annotated[int, Field(ge=0)]
    anomaly_pixel_count: Annotated[int, Field(ge=0)]
    region_count: Annotated[int, Field(ge=0)]

    @field_validator("pro_fpr_limit")
    @classmethod
    def require_frozen_pro_limit(cls, value: float) -> float:
        if value != 0.3:
            raise ValueError("pro_fpr_limit must equal the frozen value 0.30")
        return value

    @model_validator(mode="after")
    def require_metric_support_consistency(self) -> Self:
        if self.normal_pixel_count + self.anomaly_pixel_count == 0:
            raise ValueError("pixel metric support must not be empty")
        has_both_classes = self.normal_pixel_count > 0 and self.anomaly_pixel_count > 0
        discrimination_defined = self.auroc is not None and self.average_precision is not None
        if discrimination_defined != has_both_classes:
            raise ValueError("pixel AUROC and AUPR must be defined when both classes are present")
        if (self.region_count > 0) != (self.anomaly_pixel_count > 0):
            raise ValueError("region count must agree with anomalous pixel support")
        pro_defined = self.au_pro is not None
        if pro_defined != (self.normal_pixel_count > 0 and self.region_count > 0):
            raise ValueError("AU-PRO must be defined when normal pixels and anomaly regions exist")
        return self


class ConfidenceInterval(ContractModel):
    """Deterministic paired-bootstrap confidence interval for a mean delta."""

    metric_contract_version: Literal["1.0.0"] = METRIC_CONTRACT_VERSION
    estimate: Annotated[float, Field(allow_inf_nan=False)]
    lower: Annotated[float, Field(allow_inf_nan=False)]
    upper: Annotated[float, Field(allow_inf_nan=False)]
    confidence_level: Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)] = 0.95
    seed: int
    resamples: Annotated[int, Field(gt=0)]

    @field_validator("confidence_level")
    @classmethod
    def require_frozen_confidence_level(cls, value: float) -> float:
        if value != 0.95:
            raise ValueError("confidence_level must equal the frozen value 0.95")
        return value

    @model_validator(mode="after")
    def require_ordered_bounds(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("lower must not exceed upper")
        return self


class CategoryMetrics(ContractModel):
    """Frozen quality metrics retained for one MVTec AD 2 category."""

    metric_contract_version: Literal["1.0.0"] = METRIC_CONTRACT_VERSION
    image: ImageMetrics
    pixel: PixelMetrics


class MetricArtifact(ContractModel):
    """Versioned per-category evidence from one prediction-contract generation."""

    metric_contract_version: Literal["1.0.0"] = METRIC_CONTRACT_VERSION
    prediction_contract_versions: Annotated[tuple[str, ...], Field(min_length=1)]
    category_metrics: Annotated[dict[MVTecAD2Category, CategoryMetrics], Field(min_length=1)]

    @field_validator("prediction_contract_versions")
    @classmethod
    def reject_mixed_prediction_contracts(cls, versions: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(versions)) != 1:
            raise ValueError("mixed prediction-contract versions are not allowed")
        return versions
