from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from experiments.models.base import PredictionArtifact, PredictionSplit
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256
from inspection_platform.contracts.experiments import ModelFamily
from inspection_platform.drift.detector import (
    MIN_EXPECTED_SAMPLES_PER_BIN,
    PSI_EPSILON,
    PSI_HIGH_THRESHOLD,
    PSI_MODERATE_THRESHOLD,
    DriftResult,
    HistogramBin,
    ScoreSummary,
    compute_score_drift,
)

DRIFT_GENERATOR_VERSION: Final[Literal["1.0.0"]] = "1.0.0"
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
Share = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GeneratorIdentity(_FrozenModel):
    name: Literal["mvtec-ad2-offline-drift"] = "mvtec-ad2-offline-drift"
    version: Literal["1.0.0"] = DRIFT_GENERATOR_VERSION


class DriftMethod(_FrozenModel):
    name: Literal["population_stability_index"] = "population_stability_index"
    threshold_kind: Literal["heuristic_not_calibrated_production_gate"] = (
        "heuristic_not_calibrated_production_gate"
    )
    low_upper_bound_exclusive: FiniteFloat = PSI_MODERATE_THRESHOLD
    moderate_upper_bound_exclusive: FiniteFloat = PSI_HIGH_THRESHOLD
    epsilon: FiniteFloat = PSI_EPSILON
    minimum_expected_samples_per_bin: Annotated[int, Field(gt=0)] = MIN_EXPECTED_SAMPLES_PER_BIN
    quantile_method: Literal["linear"] = "linear"
    smoothing_policy: Literal["floor_each_share_then_renormalize"] = (
        "floor_each_share_then_renormalize"
    )
    duplicate_edge_policy: Literal["drop_duplicate_interior_edges"] = (
        "drop_duplicate_interior_edges"
    )
    constant_baseline_policy: Literal["below_equal_above"] = "below_equal_above"

    @model_validator(mode="after")
    def require_versioned_method_constants(self) -> Self:
        if (
            self.low_upper_bound_exclusive != PSI_MODERATE_THRESHOLD
            or self.moderate_upper_bound_exclusive != PSI_HIGH_THRESHOLD
            or self.epsilon != PSI_EPSILON
            or self.minimum_expected_samples_per_bin != MIN_EXPECTED_SAMPLES_PER_BIN
        ):
            raise ValueError(
                "epsilon, heuristic thresholds, and sample-size rule are fixed by this version"
            )
        return self


class ArtifactProvenance(_FrozenModel):
    category: MVTecAD2Category
    split: PredictionSplit
    artifact_sha256: Sha256
    artifact_schema_version: str
    prediction_record_schema_version: str
    model_family: ModelFamily
    config_sha256: Sha256
    model_bundle_id: str
    sample_count: Annotated[int, Field(gt=0)]

    @field_validator(
        "artifact_schema_version", "prediction_record_schema_version", "model_bundle_id"
    )
    @classmethod
    def require_non_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("artifact identities must be non-blank")
        return value


class DriftSource(_FrozenModel):
    description: Annotated[str, Field(min_length=1)]
    sample_count: Annotated[int, Field(gt=0)]
    artifacts: Annotated[tuple[ArtifactProvenance, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_consistent_inventory(self) -> Self:
        categories = tuple(item.category for item in self.artifacts)
        if len(categories) != len(set(categories)):
            raise ValueError("drift source contains duplicate categories")
        if categories != tuple(sorted(categories)):
            raise ValueError("drift source artifacts must be sorted by category")
        if self.sample_count != sum(item.sample_count for item in self.artifacts):
            raise ValueError("drift source sample count must equal artifact sample counts")
        return self


class DistributionSummary(_FrozenModel):
    count: Annotated[int, Field(gt=0)]
    minimum: FiniteFloat
    maximum: FiniteFloat
    mean: FiniteFloat
    standard_deviation: NonNegativeFiniteFloat
    q1: FiniteFloat
    median: FiniteFloat
    q3: FiniteFloat

    @model_validator(mode="after")
    def require_ordered_statistics(self) -> Self:
        if not (self.minimum <= self.q1 <= self.median <= self.q3 <= self.maximum):
            raise ValueError("distribution summary statistics must be ordered")
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError("distribution summary mean must fall within its range")
        return self


class HistogramSummary(_FrozenModel):
    label: str
    lower_bound: FiniteFloat | None
    upper_bound: FiniteFloat | None
    baseline_count: Annotated[int, Field(ge=0)]
    current_count: Annotated[int, Field(ge=0)]
    baseline_share: Share
    current_share: Share

    @field_validator("label")
    @classmethod
    def require_non_blank_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("histogram label must be non-blank")
        return value


class CategoryDrift(_FrozenModel):
    category: MVTecAD2Category
    model_family: ModelFamily
    config_sha256: Sha256
    model_bundle_id: str
    prediction_record_schema_version: str
    baseline_split: PredictionSplit
    current_split: PredictionSplit
    baseline: DistributionSummary
    current: DistributionSummary
    requested_bins: Annotated[int, Field(ge=2)]
    effective_bins: Annotated[int, Field(gt=0)]
    bin_strategy: Literal["baseline_quantiles", "constant_baseline_three_way"]
    histogram: Annotated[tuple[HistogramSummary, ...], Field(min_length=1)]
    psi: NonNegativeFiniteFloat
    severity: Literal["low", "moderate", "high"]
    sample_size_adequate: bool
    sample_size_note: str | None

    @field_validator("model_bundle_id", "prediction_record_schema_version")
    @classmethod
    def require_non_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("comparison identities must be non-blank")
        return value

    @model_validator(mode="after")
    def require_consistent_histogram(self) -> Self:
        if self.effective_bins != len(self.histogram):
            raise ValueError("effective_bins must equal histogram length")
        labels = tuple(item.label for item in self.histogram)
        if len(labels) != len(set(labels)):
            raise ValueError("histogram labels must be unique")
        bounds = tuple((item.lower_bound, item.upper_bound) for item in self.histogram)
        if self.bin_strategy == "constant_baseline_three_way":
            constant = self.baseline.minimum
            baseline_statistics = (
                self.baseline.maximum,
                self.baseline.mean,
                self.baseline.q1,
                self.baseline.median,
                self.baseline.q3,
            )
            if any(value != constant for value in baseline_statistics):
                raise ValueError("constant bin strategy requires a constant baseline")
            if self.baseline.standard_deviation != 0.0:
                raise ValueError("constant bin strategy requires zero baseline deviation")
            expected_labels = (
                "below_baseline_constant",
                "equal_to_baseline_constant",
                "above_baseline_constant",
            )
            expected_bounds = (
                (None, constant),
                (constant, constant),
                (constant, None),
            )
            expected_baseline_counts = (0, self.baseline.count, 0)
            if (
                labels != expected_labels
                or bounds != expected_bounds
                or tuple(item.baseline_count for item in self.histogram) != expected_baseline_counts
            ):
                raise ValueError("constant baseline histogram must use exact three-way bins")
        else:
            if self.baseline.minimum == self.baseline.maximum:
                raise ValueError("quantile bin strategy requires a nonconstant baseline")
            if not 2 <= self.effective_bins <= min(self.requested_bins, self.baseline.count):
                raise ValueError(
                    "quantile effective_bins must be between two and the sample/request limit"
                )
            if labels != tuple(f"bin_{index}" for index in range(self.effective_bins)):
                raise ValueError("quantile histogram labels must use canonical bin indexes")
            if bounds[0][0] is not None or bounds[-1][1] is not None:
                raise ValueError("quantile histogram bounds must be open-ended at both extremes")
            interior_edges: list[float] = []
            for index, item in enumerate(self.histogram):
                if (
                    item.lower_bound is not None
                    and item.upper_bound is not None
                    and item.lower_bound >= item.upper_bound
                ):
                    raise ValueError("quantile histogram bounds must be strictly ordered")
                if index < self.effective_bins - 1:
                    edge = item.upper_bound
                    next_lower = self.histogram[index + 1].lower_bound
                    if edge is None or next_lower is None or edge != next_lower:
                        raise ValueError("quantile histogram bounds must be contiguous")
                    interior_edges.append(edge)
            if interior_edges != sorted(set(interior_edges)):
                raise ValueError("quantile histogram bounds must be unique and ordered")
            if any(
                edge < self.baseline.minimum or edge > self.baseline.maximum
                for edge in interior_edges
            ):
                raise ValueError("quantile histogram bounds must lie within the baseline range")
            if any(item.baseline_count == 0 for item in self.histogram):
                raise ValueError("quantile histogram bins must contain baseline samples")
        if self.baseline.count != sum(item.baseline_count for item in self.histogram):
            raise ValueError("baseline histogram counts must equal summary count")
        if self.current.count != sum(item.current_count for item in self.histogram):
            raise ValueError("current histogram counts must equal summary count")
        for item in self.histogram:
            expected_baseline_share = item.baseline_count / self.baseline.count
            expected_current_share = item.current_count / self.current.count
            if not math.isclose(
                item.baseline_share, expected_baseline_share, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError("baseline histogram shares must match counts")
            if not math.isclose(
                item.current_share, expected_current_share, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError("current histogram shares must match counts")
        if self.sample_size_adequate != (self.sample_size_note is None):
            raise ValueError("sample-size note must agree with adequacy")
        return self


class DriftReport(ContractModel):
    report_type: Literal["offline_anomaly_score_distribution_drift"] = (
        "offline_anomaly_score_distribution_drift"
    )
    generator: GeneratorIdentity
    method: DriftMethod
    baseline: DriftSource
    current: DriftSource
    comparisons: Annotated[tuple[CategoryDrift, ...], Field(min_length=1)]
    limitations: Annotated[tuple[str, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_consistent_evidence(self) -> Self:
        baseline = {item.category: item for item in self.baseline.artifacts}
        current = {item.category: item for item in self.current.artifacts}
        categories = tuple(item.category for item in self.comparisons)
        if len(categories) != len(set(categories)):
            raise ValueError("drift report contains duplicate comparison categories")
        if categories != tuple(sorted(categories)):
            raise ValueError("drift report comparisons must be sorted by category")
        if set(categories) != set(baseline) or set(categories) != set(current):
            raise ValueError("drift report category inventories must match")
        for comparison in self.comparisons:
            baseline_item = baseline[comparison.category]
            current_item = current[comparison.category]
            if baseline_item.artifact_schema_version != current_item.artifact_schema_version:
                raise ValueError("baseline and current artifact contracts must match")
            expected_identity = (
                comparison.model_family,
                comparison.config_sha256,
                comparison.model_bundle_id,
                comparison.prediction_record_schema_version,
            )
            for source_item in (baseline_item, current_item):
                source_identity = (
                    source_item.model_family,
                    source_item.config_sha256,
                    source_item.model_bundle_id,
                    source_item.prediction_record_schema_version,
                )
                if source_identity != expected_identity:
                    raise ValueError("comparison identity must match source provenance")
            if (
                baseline_item.split != comparison.baseline_split
                or current_item.split != comparison.current_split
            ):
                raise ValueError("comparison splits must match source provenance")
            if (
                baseline_item.sample_count != comparison.baseline.count
                or current_item.sample_count != comparison.current.count
            ):
                raise ValueError("comparison counts must match source provenance")

            baseline_counts = np.array(
                [item.baseline_count for item in comparison.histogram], dtype=np.int64
            )
            current_counts = np.array(
                [item.current_count for item in comparison.histogram], dtype=np.int64
            )
            baseline_shares = np.maximum(
                baseline_counts.astype(np.float64) / comparison.baseline.count,
                self.method.epsilon,
            )
            current_shares = np.maximum(
                current_counts.astype(np.float64) / comparison.current.count,
                self.method.epsilon,
            )
            baseline_shares /= np.sum(baseline_shares)
            current_shares /= np.sum(current_shares)
            expected_psi = max(
                0.0,
                float(
                    np.sum(
                        (current_shares - baseline_shares)
                        * np.log(current_shares / baseline_shares)
                    )
                ),
            )
            if not math.isclose(comparison.psi, expected_psi, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("reported PSI must match histogram counts and smoothing policy")
            expected_severity = (
                "low"
                if comparison.psi < self.method.low_upper_bound_exclusive
                else (
                    "moderate"
                    if comparison.psi < self.method.moderate_upper_bound_exclusive
                    else "high"
                )
            )
            if comparison.severity != expected_severity:
                raise ValueError("reported severity must match heuristic PSI thresholds")
            expected_adequacy = (
                min(comparison.baseline.count, comparison.current.count)
                >= self.method.minimum_expected_samples_per_bin * comparison.effective_bins
            )
            if comparison.sample_size_adequate != expected_adequacy:
                raise ValueError("sample-size adequacy must match report method")
        return self


@dataclass(frozen=True, slots=True)
class _LoadedArtifact:
    artifact: PredictionArtifact
    artifact_sha256: str
    model_bundle_id: str
    prediction_record_schema_version: str


def _load_artifact(path: Path) -> _LoadedArtifact:
    resolved = path.expanduser().resolve(strict=True)
    payload = resolved.read_bytes()
    artifact = PredictionArtifact.model_validate_json(payload)
    if not artifact.records:
        raise ValueError(f"{artifact.category} prediction records must be non-empty")
    if any(record.category != artifact.category for record in artifact.records):
        raise ValueError(f"{artifact.category} prediction record category does not match artifact")
    bundle_ids = {record.model_bundle_id for record in artifact.records}
    if len(bundle_ids) != 1:
        raise ValueError(f"{artifact.category} prediction artifact must use one model bundle")
    model_bundle_id = next(iter(bundle_ids))
    if not model_bundle_id.strip():
        raise ValueError(f"{artifact.category} model bundle identity must be non-blank")
    record_versions = {record.schema_version for record in artifact.records}
    if len(record_versions) != 1:
        raise ValueError(f"{artifact.category} prediction artifact mixes record contract versions")
    return _LoadedArtifact(
        artifact=artifact,
        artifact_sha256=hashlib.sha256(payload).hexdigest(),
        model_bundle_id=model_bundle_id,
        prediction_record_schema_version=next(iter(record_versions)),
    )


def _load_side(paths: Sequence[Path], role: str) -> dict[MVTecAD2Category, _LoadedArtifact]:
    if not paths:
        raise ValueError(f"{role} artifacts must be non-empty")
    loaded: dict[MVTecAD2Category, _LoadedArtifact] = {}
    for path in paths:
        item = _load_artifact(path)
        category = item.artifact.category
        if category in loaded:
            raise ValueError(f"{role} contains duplicate category artifact: {category}")
        loaded[category] = item
    return loaded


def _provenance(item: _LoadedArtifact) -> ArtifactProvenance:
    artifact = item.artifact
    return ArtifactProvenance(
        category=artifact.category,
        split=artifact.split,
        artifact_sha256=item.artifact_sha256,
        artifact_schema_version=artifact.schema_version,
        prediction_record_schema_version=item.prediction_record_schema_version,
        model_family=artifact.family,
        config_sha256=artifact.config_sha256,
        model_bundle_id=item.model_bundle_id,
        sample_count=len(artifact.records),
    )


def _source(description: str, artifacts: dict[MVTecAD2Category, _LoadedArtifact]) -> DriftSource:
    provenance = tuple(_provenance(artifacts[category]) for category in sorted(artifacts))
    return DriftSource(
        description=description,
        sample_count=sum(item.sample_count for item in provenance),
        artifacts=provenance,
    )


def _summary(summary: ScoreSummary) -> DistributionSummary:
    return DistributionSummary(
        count=summary.count,
        minimum=summary.minimum,
        maximum=summary.maximum,
        mean=summary.mean,
        standard_deviation=summary.standard_deviation,
        q1=summary.q1,
        median=summary.median,
        q3=summary.q3,
    )


def _histogram(item: HistogramBin) -> HistogramSummary:
    return HistogramSummary(
        label=item.label,
        lower_bound=item.lower_bound,
        upper_bound=item.upper_bound,
        baseline_count=item.baseline_count,
        current_count=item.current_count,
        baseline_share=item.baseline_share,
        current_share=item.current_share,
    )


def _require_comparable(baseline: _LoadedArtifact, current: _LoadedArtifact) -> None:
    category = baseline.artifact.category
    if baseline.artifact.schema_version != current.artifact.schema_version:
        raise ValueError(f"{category} prediction artifact contract differs")
    if baseline.artifact.family != current.artifact.family:
        raise ValueError(f"{category} model family differs between baseline and current")
    if baseline.artifact.config_sha256 != current.artifact.config_sha256:
        raise ValueError(f"{category} model config differs between baseline and current")
    if baseline.model_bundle_id != current.model_bundle_id:
        raise ValueError(f"{category} model bundle differs between baseline and current")
    if baseline.prediction_record_schema_version != current.prediction_record_schema_version:
        raise ValueError(f"{category} prediction record contract differs")


def _comparison(baseline: _LoadedArtifact, current: _LoadedArtifact, bins: int) -> CategoryDrift:
    _require_comparable(baseline, current)
    baseline_scores = np.array(
        [record.anomaly_score for record in baseline.artifact.records], dtype=np.float64
    )
    current_scores = np.array(
        [record.anomaly_score for record in current.artifact.records], dtype=np.float64
    )
    result: DriftResult = compute_score_drift(baseline_scores, current_scores, bins=bins)
    return CategoryDrift(
        category=baseline.artifact.category,
        model_family=baseline.artifact.family,
        config_sha256=baseline.artifact.config_sha256,
        model_bundle_id=baseline.model_bundle_id,
        prediction_record_schema_version=baseline.prediction_record_schema_version,
        baseline_split=baseline.artifact.split,
        current_split=current.artifact.split,
        baseline=_summary(result.baseline),
        current=_summary(result.current),
        requested_bins=result.requested_bins,
        effective_bins=result.effective_bins,
        bin_strategy=result.strategy,
        histogram=tuple(_histogram(item) for item in result.histogram),
        psi=result.psi,
        severity=result.severity,
        sample_size_adequate=result.sample_size_adequate,
        sample_size_note=(
            None
            if result.sample_size_adequate
            else "Fewer than five samples per effective bin on at least one side."
        ),
    )


def build_drift_report(
    *,
    baseline_artifacts: Sequence[Path],
    current_artifacts: Sequence[Path],
    baseline_description: str,
    current_description: str,
    bins: int = 10,
) -> DriftReport:
    """Build a deterministic offline report from canonical prediction artifacts."""

    baseline = _load_side(baseline_artifacts, "baseline")
    current = _load_side(current_artifacts, "current")
    if set(baseline) != set(current):
        raise ValueError("baseline and current category sets must match exactly")
    comparisons = tuple(
        _comparison(baseline[category], current[category], bins) for category in sorted(baseline)
    )
    return DriftReport(
        generator=GeneratorIdentity(),
        method=DriftMethod(),
        baseline=_source(baseline_description, baseline),
        current=_source(current_description, current),
        comparisons=comparisons,
        limitations=(
            "PSI severity thresholds are heuristics, not calibrated production gates.",
            "This offline report does not establish continuous monitoring, alerting, or "
            "factory performance.",
            "Source digests identify prediction-artifact bytes; raw scores and input paths "
            "are omitted.",
        ),
    )


__all__ = ["DriftReport", "build_drift_report"]
