from __future__ import annotations

from copy import deepcopy
from statistics import fmean
from typing import Literal, Self, cast

from pydantic import model_validator

from experiments.high_resolution_patchcore import StudyComparison, StudyMetrics
from experiments.models.base import ModelConfig
from inspection_platform.contracts import RunSpec
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import Sha256

CATEGORY: Literal["wallplugs"] = "wallplugs"
REFERENCE_RATIO = 0.1
RATIOS = (0.01, 0.02)
Ratio = float
StudySeed = Literal[42, 17, 2026]
StudyVerdict = Literal[
    "EFFICIENT_REPRODUCIBLE",
    "EFFICIENT_SEED42_ONLY",
    "NO_QUALITY_PRESERVATION",
    "RESOURCE_LIMIT_EXCEEDED",
]


def _ratio(config: ModelConfig) -> float:
    value = config.family_options.get("coreset_sampling_ratio")
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        raise ValueError("PatchCore coreset_sampling_ratio must be numeric")
    return float(value)


def validate_memory_bounded_config(
    candidate: ModelConfig,
    *,
    reference: ModelConfig,
    ratio: Ratio,
) -> None:
    if ratio not in RATIOS:
        raise ValueError("declared coreset ratio must be exactly 0.01 or 0.02")
    if reference.family != "patchcore" or reference.input_size != (640, 640):
        raise ValueError("reference must be the frozen 640 x 640 PatchCore config")
    if abs(_ratio(reference) - REFERENCE_RATIO) > 1e-12:
        raise ValueError("reference must use the frozen 0.10 coreset ratio")
    if candidate.family != "patchcore" or candidate.input_size != (640, 640):
        raise ValueError("candidate must remain 640 x 640 PatchCore")
    if abs(_ratio(candidate) - ratio) > 1e-12:
        raise ValueError(f"candidate must use the declared {ratio:.2f} coreset ratio")

    expected = reference.model_dump(mode="json", exclude_computed_fields=True)
    normalized = deepcopy(candidate.model_dump(mode="json", exclude_computed_fields=True))
    family_options = normalized.get("family_options")
    if not isinstance(family_options, dict):
        raise ValueError("candidate family_options must be an object")
    family_options["coreset_sampling_ratio"] = REFERENCE_RATIO
    if normalized != expected:
        raise ValueError("candidate may change only coreset_sampling_ratio")


def build_candidate_specs(
    config_001: ModelConfig,
    config_002: ModelConfig,
    *,
    dataset_manifest_sha256: Sha256,
) -> tuple[RunSpec, ...]:
    ordered = (
        (config_001, 42),
        (config_002, 42),
        (config_001, 17),
        (config_001, 2026),
        (config_002, 17),
        (config_002, 2026),
    )
    return tuple(
        RunSpec(
            model_family="patchcore",
            category=CATEGORY,
            seed=seed,
            config=config.model_dump(mode="json", exclude_computed_fields=True),
            dataset_manifest_sha256=dataset_manifest_sha256,
        )
        for config, seed in ordered
    )


class CandidateOutcome(ContractModel):
    ratio: Ratio
    seed: StudySeed
    comparison: StudyComparison | None
    frontier_reference: StudyMetrics | None = None
    resource_ok: bool = True
    resource_reason_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def require_consistent_evidence(self) -> Self:
        if self.ratio not in RATIOS:
            raise ValueError("candidate ratio must be exactly 0.01 or 0.02")
        if self.resource_ok and self.comparison is None:
            raise ValueError("resource-safe outcome requires a completed comparison")
        if not self.resource_ok and self.resource_reason_sha256 is None:
            raise ValueError("resource failure requires a sanitized reason hash")
        if self.comparison is not None and self.comparison.category != CATEGORY:
            raise ValueError("memory-bounded outcome must be for wallplugs")
        if self.seed == 42 and self.resource_ok and self.frontier_reference is None:
            raise ValueError("seed-42 outcome requires the frozen 640 efficiency reference")
        if self.seed != 42 and self.frontier_reference is not None:
            raise ValueError("replication outcome must not contain a seed-42 efficiency reference")
        return self


def _artifact_cap_bytes(ratio: Ratio) -> int:
    return (200 if ratio == 0.01 else 350) * 1024**2


def _latency_cap_ms(ratio: Ratio) -> float:
    return 150.0 if ratio == 0.01 else 175.0


def passes_seed42_gate(outcome: CandidateOutcome) -> bool:
    comparison = outcome.comparison
    reference = outcome.frontier_reference
    if outcome.seed != 42 or not outcome.resource_ok or comparison is None or reference is None:
        return False
    candidate = comparison.candidate
    return (
        comparison.au_pro_delta >= 0.03
        and comparison.pixel_auroc_delta >= 0.0
        and comparison.image_auroc_delta >= -0.05
        and candidate.au_pro - reference.au_pro >= -0.02
        and candidate.pixel_auroc - reference.pixel_auroc >= -0.005
        and candidate.image_auroc - reference.image_auroc >= -0.01
        and candidate.gpu_p95_latency_ms <= _latency_cap_ms(outcome.ratio)
        and candidate.artifact_size_bytes <= _artifact_cap_bytes(outcome.ratio)
        and candidate.per_image_failure_rate == 0.0
    )


def select_ratio(probes: tuple[CandidateOutcome, ...]) -> Ratio | None:
    if len(probes) not in (1, 2):
        raise ValueError("ratio selection requires one or two ordered probes")
    expected = (0.01, 0.02)[: len(probes)]
    if tuple(probe.ratio for probe in probes) != expected:
        raise ValueError("probe ratios must follow the frozen 0.01 then 0.02 order")
    for probe in probes:
        if passes_seed42_gate(probe):
            return probe.ratio
    return None


def _spec_ratio(spec: RunSpec) -> float:
    options = spec.config.get("family_options")
    if not isinstance(options, dict):
        raise ValueError("candidate spec family_options must be an object")
    value = options.get("coreset_sampling_ratio")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("candidate spec coreset ratio must be numeric")
    return float(value)


def select_next_specs(
    specs: tuple[RunSpec, ...],
    *,
    probes: tuple[CandidateOutcome, ...],
) -> tuple[RunSpec, ...]:
    expected = ((0.01, 42), (0.02, 42), (0.01, 17), (0.01, 2026), (0.02, 17), (0.02, 2026))
    observed = tuple((_spec_ratio(spec), spec.seed) for spec in specs)
    if observed != expected:
        raise ValueError("candidate specs differ from the frozen ratio and seed ladder")
    if not probes:
        return specs[:1]
    if len(probes) == 1:
        probe = probes[0]
        if probe.ratio != 0.01 or not probe.resource_ok:
            return ()
        return specs[2:4] if passes_seed42_gate(probe) else specs[1:2]
    if len(probes) == 2:
        if probes[0].ratio != 0.01 or probes[1].ratio != 0.02:
            raise ValueError("probe outcomes differ from the frozen ratio ladder")
        if not probes[1].resource_ok:
            return ()
        return specs[4:6] if passes_seed42_gate(probes[1]) else ()
    raise ValueError("candidate ladder cannot contain more than two probes")


def classify_memory_bounded_study(
    outcomes: tuple[CandidateOutcome, CandidateOutcome, CandidateOutcome],
) -> StudyVerdict:
    if any(not outcome.resource_ok or outcome.comparison is None for outcome in outcomes):
        return "RESOURCE_LIMIT_EXCEEDED"
    ratio = outcomes[0].ratio
    if tuple(outcome.seed for outcome in outcomes) != (42, 17, 2026) or any(
        outcome.ratio != ratio for outcome in outcomes
    ):
        raise ValueError("final outcomes must contain one selected ratio at seeds 42, 17, 2026")
    comparisons = tuple(cast(StudyComparison, outcome.comparison) for outcome in outcomes)
    au_pro = tuple(item.au_pro_delta for item in comparisons)
    image = tuple(item.image_auroc_delta for item in comparisons)
    pixel = tuple(item.pixel_auroc_delta for item in comparisons)
    resource_safe = all(
        item.candidate.gpu_p95_latency_ms <= 175.0
        and item.candidate.artifact_size_bytes <= _artifact_cap_bytes(ratio)
        and item.candidate.per_image_failure_rate == 0.0
        for item in comparisons
    )
    if not resource_safe:
        return "RESOURCE_LIMIT_EXCEEDED"
    if (
        fmean(au_pro) >= 0.02
        and sum(delta > 0.0 for delta in au_pro) >= 2
        and fmean(image) >= -0.04
        and min(image) >= -0.07
        and fmean(pixel) >= 0.0
    ):
        return "EFFICIENT_REPRODUCIBLE"
    return "EFFICIENT_SEED42_ONLY"


__all__ = [
    "CandidateOutcome",
    "StudyVerdict",
    "build_candidate_specs",
    "classify_memory_bounded_study",
    "passes_seed42_gate",
    "select_next_specs",
    "select_ratio",
    "validate_memory_bounded_config",
]
