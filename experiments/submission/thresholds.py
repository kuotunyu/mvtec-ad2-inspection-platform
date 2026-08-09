from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, computed_field

from experiments.models.base import PredictionArtifact
from inspection_platform.contracts import canonical_hash, sha256_file
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256


@dataclass(frozen=True, slots=True)
class PopulationStatistics:
    pixel_count: int
    mean: float
    standard_deviation: float
    threshold: float


class SubmissionThreshold(ContractModel):
    method: Literal["validation_pixel_mean_plus_3_population_std"] = (
        "validation_pixel_mean_plus_3_population_std"
    )
    calibration_split: Literal["validation/good"] = "validation/good"
    category: MVTecAD2Category
    run_identity: Sha256
    validation_artifact_sha256: Sha256
    pixel_count: Annotated[int, Field(gt=0)]
    mean: Annotated[float, Field(allow_inf_nan=False)]
    standard_deviation: Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
    threshold: Annotated[float, Field(allow_inf_nan=False)]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


def combine_population_statistics(
    arrays: Iterable[NDArray[np.floating[Any]]],
) -> PopulationStatistics:
    pixel_count = 0
    mean = 0.0
    sum_squared_deviations = 0.0
    for array in arrays:
        checked = np.asarray(array, dtype=np.float64)
        if checked.ndim != 2 or checked.size == 0 or not np.isfinite(checked).all():
            raise ValueError("threshold calibration requires a non-empty finite 2D anomaly map")
        chunk_count = checked.size
        chunk_mean = float(checked.mean())
        chunk_sum_squared_deviations = float(np.square(checked - chunk_mean).sum(dtype=np.float64))
        delta = chunk_mean - mean
        combined_count = pixel_count + chunk_count
        mean += delta * chunk_count / combined_count
        sum_squared_deviations += (
            chunk_sum_squared_deviations
            + delta * delta * pixel_count * chunk_count / combined_count
        )
        pixel_count = combined_count
    if pixel_count == 0:
        raise ValueError("threshold calibration requires at least one non-empty finite 2D map")
    standard_deviation = math.sqrt(sum_squared_deviations / pixel_count)
    return PopulationStatistics(
        pixel_count=pixel_count,
        mean=mean,
        standard_deviation=standard_deviation,
        threshold=mean + 3 * standard_deviation,
    )


def calibrate_submission_threshold(run_dir: Path) -> SubmissionThreshold:
    root = run_dir.expanduser().resolve(strict=True)
    spec = _load_json_object(root / "spec.json")
    record = _load_json_object(root / "record.json")
    if spec.get("seed") != 42:
        raise ValueError("submission threshold calibration requires a seed-42 run")
    if record.get("status") != "completed":
        raise ValueError("submission threshold calibration requires a completed run")
    if spec.get("canonical_sha256") != root.name:
        raise ValueError("run spec canonical identity does not match its directory")
    recorded_spec = {key: value for key, value in spec.items() if key != "canonical_sha256"}
    if record.get("spec") != recorded_spec:
        raise ValueError("run record spec does not match spec.json")

    validation_path = root / "predictions" / "validation.json"
    artifact = PredictionArtifact.model_validate_json(validation_path.read_text(encoding="utf-8"))
    if artifact.split != "validation":
        raise ValueError("threshold calibration artifact must use the validation split")
    if artifact.category != spec.get("category") or artifact.family != spec.get("model_family"):
        raise ValueError("threshold calibration artifact does not match the run spec")

    def verified_maps() -> Iterable[NDArray[np.floating[Any]]]:
        for declared in artifact.anomaly_maps:
            path = declared.path.expanduser().resolve(strict=True)
            try:
                path.relative_to(root)
            except ValueError as error:
                raise ValueError("validation anomaly map is outside the run directory") from error
            if path.stat().st_size != declared.size:
                raise ValueError("validation anomaly-map size differs from its artifact contract")
            if sha256_file(path) != declared.sha256:
                raise ValueError("validation anomaly-map hash differs from its artifact contract")
            yield cast(NDArray[np.floating[Any]], np.load(path, allow_pickle=False))

    statistics = combine_population_statistics(verified_maps())
    return SubmissionThreshold(
        category=cast(Any, spec.get("category")),
        run_identity=root.name,
        validation_artifact_sha256=sha256_file(validation_path),
        pixel_count=statistics.pixel_count,
        mean=statistics.mean,
        standard_deviation=statistics.standard_deviation,
        threshold=statistics.threshold,
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return cast(dict[str, Any], payload)
