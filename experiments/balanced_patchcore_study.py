from __future__ import annotations

from copy import deepcopy
from statistics import fmean
from typing import Literal

from experiments.high_resolution_patchcore import StudyComparison
from experiments.models.base import ModelConfig
from inspection_platform.contracts import RunSpec
from inspection_platform.contracts.dataset import Sha256

CATEGORY: Literal["wallplugs"] = "wallplugs"
BASELINE_RESOLUTION = (512, 512)
StageAVerdict = Literal[
    "REPRODUCIBLE_LOCALIZATION_GAIN",
    "MIXED",
    "NO_CLEAR_GAIN",
    "RESOURCE_LIMIT_EXCEEDED",
]
StageBVerdict = Literal["BALANCED_PROMISING", "MIXED", "NO_CLEAR_GAIN", "RESOURCE_LIMIT_EXCEEDED"]


def validate_balanced_config(
    candidate: ModelConfig,
    *,
    baseline: ModelConfig,
    resolution: tuple[int, int],
) -> None:
    if baseline.family != "patchcore" or baseline.input_size != BASELINE_RESOLUTION:
        raise ValueError("baseline must be the frozen 512 x 512 PatchCore config")
    if candidate.family != "patchcore" or candidate.input_size != resolution:
        raise ValueError(
            f"candidate must use the declared {resolution[0]} x {resolution[1]} geometry"
        )
    baseline_payload = baseline.model_dump(mode="json", exclude_computed_fields=True)
    normalized = deepcopy(candidate.model_dump(mode="json", exclude_computed_fields=True))
    normalized["input_size"] = list(BASELINE_RESOLUTION)
    preprocessing = normalized.get("preprocessing")
    if not isinstance(preprocessing, dict):
        raise ValueError("candidate preprocessing must be an object")
    preprocessing["resize"] = list(BASELINE_RESOLUTION)
    if normalized != baseline_payload:
        raise ValueError("candidate may change only input_size and preprocessing.resize")


def build_candidate_specs(
    config_640: ModelConfig,
    config_576: ModelConfig,
    *,
    dataset_manifest_sha256: Sha256,
) -> tuple[RunSpec, ...]:
    return tuple(
        RunSpec(
            model_family="patchcore",
            category=CATEGORY,
            seed=seed,
            config=config.model_dump(mode="json", exclude_computed_fields=True),
            dataset_manifest_sha256=dataset_manifest_sha256,
        )
        for config, seed in (
            (config_640, 17),
            (config_640, 2026),
            (config_576, 42),
            (config_576, 17),
            (config_576, 2026),
        )
    )


def _resource_breach(comparison: StudyComparison) -> bool:
    return (
        comparison.candidate.gpu_p95_latency_ms > 500.0
        or comparison.candidate.per_image_failure_rate != 0.0
    )


def classify_stage_a(
    comparisons: tuple[StudyComparison, StudyComparison, StudyComparison],
    *,
    failed: bool = False,
) -> StageAVerdict:
    if failed or any(_resource_breach(item) for item in comparisons):
        return "RESOURCE_LIMIT_EXCEEDED"
    deltas = [item.au_pro_delta for item in comparisons]
    if fmean(deltas) >= 0.02 and sum(delta > 0 for delta in deltas) >= 2:
        return "REPRODUCIBLE_LOCALIZATION_GAIN"
    if any(delta >= 0.02 for delta in deltas):
        return "MIXED"
    return "NO_CLEAR_GAIN"


def passes_stage_b_advance(comparison: StudyComparison) -> bool:
    return (
        not _resource_breach(comparison)
        and comparison.au_pro_delta >= 0.02
        and comparison.image_auroc_delta >= -0.01
        and comparison.pixel_auroc_delta >= -0.005
    )


def classify_stage_b(
    comparisons: tuple[StudyComparison, StudyComparison, StudyComparison],
    *,
    failed: bool = False,
) -> StageBVerdict:
    if failed or any(_resource_breach(item) for item in comparisons):
        return "RESOURCE_LIMIT_EXCEEDED"
    au_pro = [item.au_pro_delta for item in comparisons]
    image = [item.image_auroc_delta for item in comparisons]
    pixel = [item.pixel_auroc_delta for item in comparisons]
    if (
        fmean(au_pro) >= 0.02
        and fmean(image) >= -0.01
        and min(image) >= -0.03
        and fmean(pixel) >= 0.0
    ):
        return "BALANCED_PROMISING"
    if any(delta >= 0.02 for delta in au_pro):
        return "MIXED"
    return "NO_CLEAR_GAIN"
