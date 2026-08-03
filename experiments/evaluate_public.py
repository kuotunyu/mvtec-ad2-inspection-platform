from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, Self, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, computed_field, model_validator

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.metrics.artifacts import ImageMetrics, PixelMetrics, ThresholdResult
from experiments.metrics.image import compute_image_metrics
from experiments.metrics.pixel import compute_pixel_metrics
from experiments.models.base import FitArtifact, ModelConfig, PredictionArtifact
from experiments.models.factory import create_adapter
from experiments.orchestration.gpu_lock import GpuLease
from experiments.orchestration.queue import APPROVED_FAMILIES, ExperimentStage, expand_stage
from experiments.orchestration.supervisor import RunStore
from experiments.run_matrix import _manifest_images, _predict_or_reuse
from experiments.train import load_dataset_manifest
from inspection_platform.contracts import ModelFamily, RunSpec, canonical_hash, sha256_file
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256


class PublicGateError(RuntimeError):
    """Raised when frozen screening evidence cannot cross the one-way public gate."""


class OperatingPointMetrics(ContractModel):
    threshold: Annotated[float, Field(allow_inf_nan=False)]
    public_normal_false_review_rate: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    public_anomaly_recall: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    public_review_precision: Annotated[float | None, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    public_review_f1: Annotated[float | None, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    expected_reviews_per_1000_normal: Annotated[
        float, Field(ge=0.0, le=1000.0, allow_inf_nan=False)
    ]


class LatencyMetrics(ContractModel):
    device: Literal["gpu"] = "gpu"
    batch_size: Literal[1] = 1
    samples: Annotated[int, Field(gt=0)]
    p50_ms: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    p95_ms: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    throughput_images_per_second: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    setup_latency_ms: Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class PublicRunMetrics(ContractModel):
    evaluation_size: tuple[Annotated[int, Field(gt=0)], Annotated[int, Field(gt=0)]] = (
        256,
        256,
    )
    image: ImageMetrics
    pixel: PixelMetrics
    operating: OperatingPointMetrics
    gpu_latency: LatencyMetrics
    peak_vram_mib: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    artifact_size_bytes: Annotated[int, Field(gt=0)]
    per_image_failure_rate: Annotated[float, Field(ge=0.0, le=0.0)] = 0.0


def compute_public_run_metrics(
    *,
    labels: NDArray[np.int64],
    scores: NDArray[np.float64],
    masks: NDArray[np.bool_],
    maps: NDArray[np.float64],
    threshold: float,
    device_latency_ms: Sequence[float],
    setup_latency_ms: float,
    peak_vram_mib: float,
    artifact_size_bytes: int,
) -> PublicRunMetrics:
    """Compute the frozen aggregate contract without retaining image-level evidence."""

    checked_labels = np.asarray(labels, dtype=np.int64)
    checked_scores = np.asarray(scores, dtype=np.float64)
    latencies = np.asarray(device_latency_ms, dtype=np.float64)
    if len(latencies) != len(checked_labels) or len(latencies) == 0:
        raise ValueError("latency samples must align with public images")
    if not np.isfinite(latencies).all() or np.any(latencies <= 0):
        raise ValueError("latency samples must be positive and finite")
    reviews = checked_scores >= threshold
    normal = checked_labels == 0
    anomaly = checked_labels == 1
    if not normal.any() or not anomaly.any():
        raise ValueError("public metrics require normal and anomalous images")
    true_reviews = int(np.count_nonzero(reviews & anomaly))
    review_count = int(np.count_nonzero(reviews))
    anomaly_count = int(np.count_nonzero(anomaly))
    false_review_rate = float(np.mean(reviews[normal]))
    recall = true_reviews / anomaly_count
    precision = true_reviews / review_count if review_count else None
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision is not None and precision + recall > 0
        else None
    )
    return PublicRunMetrics(
        image=compute_image_metrics(checked_labels, checked_scores),
        pixel=compute_pixel_metrics(masks, maps),
        operating=OperatingPointMetrics(
            threshold=threshold,
            public_normal_false_review_rate=false_review_rate,
            public_anomaly_recall=recall,
            public_review_precision=precision,
            public_review_f1=f1,
            expected_reviews_per_1000_normal=false_review_rate * 1000.0,
        ),
        gpu_latency=LatencyMetrics(
            samples=len(latencies),
            p50_ms=float(np.percentile(latencies, 50, method="linear")),
            p95_ms=float(np.percentile(latencies, 95, method="linear")),
            throughput_images_per_second=float(1000.0 / np.mean(latencies)),
            setup_latency_ms=setup_latency_ms,
        ),
        peak_vram_mib=peak_vram_mib,
        artifact_size_bytes=artifact_size_bytes,
    )


class FrozenRunEvidence(ContractModel):
    spec: RunSpec
    record_sha256: Sha256
    artifacts: dict[str, Sha256]


class FrozenStageManifest(ContractModel):
    experiment_version: str
    stage: Literal["screening"] = "screening"
    dataset_manifest_sha256: Sha256
    runs: Annotated[tuple[FrozenRunEvidence, ...], Field(min_length=24, max_length=24)]

    @model_validator(mode="after")
    def require_complete_screening_matrix(self) -> Self:
        identities = [item.spec.identity for item in self.runs]
        if len(set(identities)) != 24:
            raise ValueError("frozen screening stage must contain 24 unique runs")
        observed = {
            (item.spec.category, item.spec.model_family, item.spec.seed) for item in self.runs
        }
        expected = {
            (category, family, 42)
            for category in REQUIRED_CATEGORIES
            for family in APPROVED_FAMILIES
        }
        if observed != expected:
            raise ValueError("frozen screening stage does not match the 3x8 seed-42 matrix")
        if any(
            item.spec.dataset_manifest_sha256 != self.dataset_manifest_sha256 for item in self.runs
        ):
            raise ValueError("frozen runs do not share the stage dataset identity")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


class PublicGateEvent(ContractModel):
    event: Literal["public_gate_opened"] = "public_gate_opened"
    experiment_version: str
    stage_manifest_identity: Sha256
    stage_manifest_file_sha256: Sha256
    dataset_manifest_sha256: Sha256
    opened_at: Annotated[float, Field(ge=0)]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


FrozenContract = FrozenStageManifest | PublicGateEvent


def _write_contract_file(path: Path, contract: FrozenContract) -> Path:
    resolved = path.expanduser().resolve()
    payload = contract.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = contract.identity
    if resolved.exists():
        if json.loads(resolved.read_text(encoding="utf-8")) != payload:
            raise PublicGateError(f"refusing to overwrite frozen evidence: {resolved}")
        return resolved
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_suffix(f"{resolved.suffix}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, resolved)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return resolved


def _load_contract(
    path: Path, model: type[FrozenStageManifest] | type[PublicGateEvent]
) -> FrozenContract:
    resolved = path.expanduser().resolve(strict=True)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublicGateError("frozen evidence root must be an object")
    canonical = payload.pop("canonical_sha256", None)
    contract = model.model_validate(cast(dict[str, Any], payload))
    if canonical != contract.identity:
        raise PublicGateError("frozen evidence canonical identity mismatch")
    return contract


def freeze_screening_stage(
    store: RunStore,
    specs: Sequence[RunSpec],
    *,
    experiment_version: str,
) -> FrozenStageManifest:
    if len(specs) != 24 or any(store.inspect(spec) != "completed" for spec in specs):
        raise PublicGateError("public gate requires exactly 24 completed hash-valid runs")
    dataset_hashes = {spec.dataset_manifest_sha256 for spec in specs}
    if len(dataset_hashes) != 1 or None in dataset_hashes:
        raise PublicGateError("screening runs must share one non-null dataset identity")
    evidence = []
    for spec in sorted(specs, key=lambda item: (item.category, item.model_family, item.seed)):
        run_dir = store.run_dir(spec)
        record = store.load_record(run_dir)
        evidence.append(
            FrozenRunEvidence(
                spec=spec,
                record_sha256=sha256_file(run_dir / "record.json"),
                artifacts=record.artifacts,
            )
        )
    return FrozenStageManifest(
        experiment_version=experiment_version,
        dataset_manifest_sha256=cast(str, dataset_hashes.pop()),
        runs=tuple(evidence),
    )


def write_frozen_stage(path: Path, manifest: FrozenStageManifest) -> Path:
    return _write_contract_file(path, manifest)


def verify_public_gate(stage_manifest_path: Path, gate_path: Path) -> PublicGateEvent:
    stage = cast(
        FrozenStageManifest,
        _load_contract(stage_manifest_path, FrozenStageManifest),
    )
    gate = cast(PublicGateEvent, _load_contract(gate_path, PublicGateEvent))
    if (
        gate.stage_manifest_identity != stage.identity
        or gate.stage_manifest_file_sha256 != sha256_file(stage_manifest_path.resolve(strict=True))
        or gate.dataset_manifest_sha256 != stage.dataset_manifest_sha256
        or gate.experiment_version != stage.experiment_version
    ):
        raise PublicGateError("stage manifest changed after the public gate was opened")
    return gate


def open_public_gate(
    stage_manifest_path: Path,
    gate_path: Path,
    *,
    clock: Callable[[], float] = time.time,
) -> PublicGateEvent:
    if gate_path.exists():
        return verify_public_gate(stage_manifest_path, gate_path)
    stage = cast(
        FrozenStageManifest,
        _load_contract(stage_manifest_path, FrozenStageManifest),
    )
    event = PublicGateEvent(
        experiment_version=stage.experiment_version,
        stage_manifest_identity=stage.identity,
        stage_manifest_file_sha256=sha256_file(stage_manifest_path.resolve(strict=True)),
        dataset_manifest_sha256=stage.dataset_manifest_sha256,
        opened_at=float(clock()),
    )
    _write_contract_file(gate_path, event)
    return event


class BenchmarkRunEvidence(ContractModel):
    stage: Literal["screening", "replication"]
    run_identity: Sha256
    family: ModelFamily
    category: MVTecAD2Category
    seed: int
    dataset_manifest_sha256: Sha256
    code_revision: str
    config_sha256: Sha256
    environment_lock_sha256: Sha256
    model_revision: str
    checkpoint_sha256: Sha256
    threshold_artifact_sha256: Sha256
    prediction_artifact_sha256: Sha256
    prediction_locator: str
    run_record_sha256: Sha256
    metrics: PublicRunMetrics

    @model_validator(mode="after")
    def require_external_relative_locator(self) -> Self:
        locator = Path(self.prediction_locator)
        if locator.is_absolute() or ".." in locator.parts:
            raise ValueError("prediction locator must be relative to the external runs root")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


class MacroMetricSummary(ContractModel):
    mean: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    lower: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    upper: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    confidence_level: Annotated[float, Field(ge=0.95, le=0.95)] = 0.95
    bootstrap_seed: int = 42
    bootstrap_resamples: Annotated[int, Field(gt=0)] = 10_000

    @model_validator(mode="after")
    def require_ordered_interval(self) -> Self:
        if not self.lower <= self.mean <= self.upper:
            raise ValueError("macro mean must lie within its confidence interval")
        return self


class ScreeningMacroEvidence(ContractModel):
    family: ModelFamily
    au_pro: MacroMetricSummary
    image_auroc: MacroMetricSummary
    run_identities: Annotated[tuple[Sha256, ...], Field(min_length=8, max_length=8)]


class PublicBenchmark(ContractModel):
    experiment_version: str
    dataset_manifest_sha256: Sha256
    public_gate_identity: Sha256
    evaluation_size: tuple[Literal[256], Literal[256]] = (256, 256)
    runs: Annotated[tuple[BenchmarkRunEvidence, ...], Field(min_length=24)]
    screening_macro: Annotated[
        tuple[ScreeningMacroEvidence, ...], Field(min_length=3, max_length=3)
    ] = ()

    @model_validator(mode="after")
    def require_consistent_unique_evidence(self) -> Self:
        identities = [run.run_identity for run in self.runs]
        if len(identities) != len(set(identities)):
            raise ValueError("public benchmark contains duplicate run identities")
        if any(
            run.dataset_manifest_sha256 != self.dataset_manifest_sha256
            or run.metrics.evaluation_size != self.evaluation_size
            for run in self.runs
        ):
            raise ValueError("public benchmark run evidence is incompatible")
        expected_macro = _screening_macro(self.runs)
        if self.screening_macro and self.screening_macro != expected_macro:
            raise ValueError("screening macro evidence differs from frozen run evidence")
        if not self.screening_macro:
            object.__setattr__(self, "screening_macro", expected_macro)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


def _macro_metric(values: NDArray[np.float64]) -> MacroMetricSummary:
    generator = np.random.default_rng(42)
    indices = generator.integers(0, len(values), size=(10_000, len(values)))
    means = values[indices].mean(axis=1)
    lower, upper = np.quantile(means, (0.025, 0.975), method="linear")
    return MacroMetricSummary(
        mean=float(values.mean()),
        lower=float(lower),
        upper=float(upper),
    )


def _screening_macro(
    runs: Sequence[BenchmarkRunEvidence],
) -> tuple[ScreeningMacroEvidence, ...]:
    summaries: list[ScreeningMacroEvidence] = []
    for family in APPROVED_FAMILIES:
        family_runs = sorted(
            (
                run
                for run in runs
                if run.stage == "screening" and run.family == family and run.seed == 42
            ),
            key=lambda run: run.category,
        )
        if len(family_runs) != 8 or {run.category for run in family_runs} != set(
            REQUIRED_CATEGORIES
        ):
            raise ValueError(f"public benchmark requires eight seed-42 {family} runs")
        if any(
            run.metrics.pixel.au_pro is None or run.metrics.image.auroc is None
            for run in family_runs
        ):
            raise ValueError("screening macro metrics must be defined")
        summaries.append(
            ScreeningMacroEvidence(
                family=family,
                au_pro=_macro_metric(
                    np.asarray(
                        [cast(float, run.metrics.pixel.au_pro) for run in family_runs],
                        dtype=np.float64,
                    )
                ),
                image_auroc=_macro_metric(
                    np.asarray(
                        [cast(float, run.metrics.image.auroc) for run in family_runs],
                        dtype=np.float64,
                    )
                ),
                run_identities=tuple(run.run_identity for run in family_runs),
            )
        )
    return tuple(summaries)


def _canonical_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _write_identity_contract(path: Path, contract: ContractModel) -> Path:
    resolved = path.expanduser().resolve()
    payload = contract.model_dump(mode="json", exclude_computed_fields=True)
    identity = getattr(contract, "identity", None)
    if not isinstance(identity, str):
        raise TypeError("identity contract must expose a canonical identity")
    payload["canonical_sha256"] = identity
    if resolved.exists():
        existing = json.loads(resolved.read_text(encoding="utf-8"))
        if existing != payload:
            raise PublicGateError(f"refusing to overwrite frozen evidence: {resolved}")
        return resolved
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_suffix(f"{resolved.suffix}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, resolved)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return resolved


def _load_identity_contract(path: Path, model: type[ContractModel]) -> ContractModel:
    payload = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublicGateError("evidence root must be an object")
    canonical = payload.pop("canonical_sha256", None)
    contract = model.model_validate(cast(dict[str, Any], payload))
    if canonical != getattr(contract, "identity", None):
        raise PublicGateError("evidence canonical identity mismatch")
    return contract


def load_public_benchmark(path: Path) -> PublicBenchmark:
    return cast(PublicBenchmark, _load_identity_contract(path, PublicBenchmark))


def write_public_benchmark(path: Path, benchmark: PublicBenchmark) -> Path:
    """Append compatible runs while refusing mutation of already-frozen entries."""

    resolved = path.expanduser().resolve()
    if resolved.exists():
        previous = load_public_benchmark(resolved)
        if (
            previous.experiment_version != benchmark.experiment_version
            or previous.dataset_manifest_sha256 != benchmark.dataset_manifest_sha256
            or previous.public_gate_identity != benchmark.public_gate_identity
        ):
            raise PublicGateError("public benchmark identity changed between stages")
        new_by_id = {run.run_identity: run for run in benchmark.runs}
        if any(new_by_id.get(run.run_identity) != run for run in previous.runs):
            raise PublicGateError("refusing to mutate frozen public run evidence")
        if previous == benchmark:
            return resolved
        temporary = resolved.with_suffix(f"{resolved.suffix}.tmp")
        payload = benchmark.model_dump(mode="json", exclude_computed_fields=True)
        payload["canonical_sha256"] = benchmark.identity
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, resolved)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return resolved
    return _write_identity_contract(resolved, benchmark)


def _load_frozen_queue(path: Path, stage_name: str) -> tuple[ExperimentStage, list[RunSpec]]:
    payload = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublicGateError("frozen queue root must be an object")
    canonical = payload.pop("canonical_sha256", None)
    if canonical != _canonical_json_hash(cast(dict[str, Any], payload)):
        raise PublicGateError("frozen queue canonical identity mismatch")
    stage = ExperimentStage.model_validate(payload.get("stage"))
    if stage.name != stage_name:
        raise PublicGateError("frozen queue stage differs from requested stage")
    raw_runs = payload.get("runs")
    if not isinstance(raw_runs, list):
        raise PublicGateError("frozen queue runs must be an array")
    runs = [RunSpec.model_validate(item) for item in raw_runs]
    if runs != expand_stage(stage):
        raise PublicGateError("frozen queue does not match deterministic stage expansion")
    return stage, runs


def _resize_array(
    array: NDArray[np.generic], size: tuple[int, int], *, nearest: bool
) -> NDArray[np.float64]:
    from PIL import Image

    image = Image.fromarray(np.asarray(array, dtype=np.float32), mode="F")
    resampling = Image.Resampling.NEAREST if nearest else Image.Resampling.BILINEAR
    resized = image.resize((size[1], size[0]), resample=resampling)
    return np.asarray(resized, dtype=np.float64)


def _metric_arrays(
    artifact: PredictionArtifact,
    *,
    evaluation_size: tuple[int, int] = (256, 256),
) -> tuple[
    NDArray[np.int64],
    NDArray[np.float64],
    NDArray[np.bool_],
    NDArray[np.float64],
]:
    labels: list[int] = []
    scores: list[float] = []
    masks: list[NDArray[np.bool_]] = []
    maps: list[NDArray[np.float64]] = []
    for record, map_file in zip(artifact.records, artifact.anomaly_maps, strict=True):
        if record.input_path is None:
            raise PublicGateError("public prediction record lacks its external source path")
        image_path = record.input_path.expanduser().resolve(strict=True)
        if sha256_file(image_path) != record.input_sha256:
            raise PublicGateError("public source image changed after prediction")
        defect = image_path.parent.name
        if defect not in {"good", "bad"}:
            raise PublicGateError("public prediction source has an unexpected defect label")
        label = int(defect == "bad")
        if label:
            mask_path = (
                image_path.parent.parent / "ground_truth" / "bad" / f"{image_path.stem}_mask.png"
            )
            from PIL import Image

            with Image.open(mask_path.resolve(strict=True)) as image:
                raw_mask = np.asarray(image.convert("L"), dtype=np.float32)
            mask = _resize_array(raw_mask, evaluation_size, nearest=True) > 0
        else:
            mask = np.zeros(evaluation_size, dtype=np.bool_)
        if not map_file.path.is_file() or sha256_file(map_file.path) != map_file.sha256:
            raise PublicGateError("public anomaly map is missing or corrupt")
        anomaly_map = np.load(map_file.path, allow_pickle=False)
        labels.append(label)
        scores.append(record.anomaly_score)
        masks.append(mask)
        maps.append(_resize_array(anomaly_map, evaluation_size, nearest=False))
    return (
        np.asarray(labels, dtype=np.int64),
        np.asarray(scores, dtype=np.float64),
        np.stack(masks),
        np.stack(maps),
    )


def _load_fit_artifact(run_dir: Path, spec: RunSpec, config: ModelConfig) -> FitArtifact:
    path = run_dir / "checkpoints" / "fit-artifact.json"
    artifact = FitArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    if (
        artifact.family != spec.model_family
        or artifact.category != spec.category
        or artifact.seed != spec.seed
        or artifact.config_sha256 != config.identity
        or sha256_file(artifact.checkpoint.path) != artifact.checkpoint.sha256
    ):
        raise PublicGateError("fit artifact is incompatible with frozen run evidence")
    return artifact


def _evaluate_run(
    *,
    store: RunStore,
    spec: RunSpec,
    stage: Literal["screening", "replication"],
    data_root: Path,
    dataset_manifest: Path,
    evaluation_root: Path,
    device: str,
    imagenette_root: Path | None,
) -> BenchmarkRunEvidence:
    evidence_path = evaluation_root / spec.identity / "public-run.json"
    if evidence_path.exists():
        evidence = cast(
            BenchmarkRunEvidence,
            _load_identity_contract(evidence_path, BenchmarkRunEvidence),
        )
        if evidence.run_identity != spec.identity or evidence.stage != stage:
            raise PublicGateError("existing public evidence differs from requested run")
        if store.inspect(spec) != "completed":
            raise PublicGateError("source run changed after public evidence was frozen")
        prediction_path = (store.root / evidence.prediction_locator).resolve(strict=True)
        if (
            sha256_file(prediction_path) != evidence.prediction_artifact_sha256
            or sha256_file(store.run_dir(spec) / "record.json") != evidence.run_record_sha256
        ):
            raise PublicGateError("public evidence source hash changed")
        prediction = PredictionArtifact.model_validate_json(
            prediction_path.read_text(encoding="utf-8")
        )
        if any(
            not item.path.is_file() or sha256_file(item.path) != item.sha256
            for item in prediction.anomaly_maps
        ):
            raise PublicGateError("public anomaly-map evidence changed")
        return evidence

    if store.inspect(spec) != "completed":
        raise PublicGateError(f"public evaluation requires completed run {spec.identity}")
    run_dir = store.run_dir(spec)
    record = store.load_record(run_dir)
    required_record_fields = (
        record.code_revision,
        record.environment_lock_sha256,
        record.model_revision,
    )
    if any(value is None for value in required_record_fields):
        raise PublicGateError("completed run lacks reproducibility evidence")
    config = ModelConfig.model_validate(spec.config)
    fit = _load_fit_artifact(run_dir, spec, config)
    threshold_path = run_dir / "metrics" / "threshold.json"
    threshold = ThresholdResult.model_validate_json(threshold_path.read_text(encoding="utf-8"))
    public_root = evidence_path.parent
    auxiliary_roots = {"imagenette": imagenette_root} if imagenette_root is not None else {}

    import torch

    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    adapter = create_adapter(spec.model_family, config)
    prediction = _predict_or_reuse(
        adapter=adapter,
        spec=spec,
        config=config,
        checkpoint=fit.checkpoint.path,
        images=_manifest_images(
            data_root,
            load_dataset_manifest(dataset_manifest),
            prefix=f"{spec.category}/test_public/",
            exclude_ground_truth=True,
        ),
        split="test_public",
        predictions_root=public_root / "predictions",
        device=device,
        auxiliary_roots=auxiliary_roots,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if not prediction.device_latency_ms:
        raise PublicGateError("public prediction lacks frozen per-image device latency")
    labels, scores, masks, maps = _metric_arrays(prediction)
    metrics = compute_public_run_metrics(
        labels=labels,
        scores=scores,
        masks=masks,
        maps=maps,
        threshold=threshold.threshold,
        device_latency_ms=prediction.device_latency_ms,
        setup_latency_ms=max(0.0, elapsed_ms - sum(prediction.device_latency_ms)),
        peak_vram_mib=float(torch.cuda.max_memory_allocated() / 1024**2),
        artifact_size_bytes=fit.checkpoint.size,
    )
    prediction_path = public_root / "predictions" / "test_public.json"
    evidence = BenchmarkRunEvidence(
        stage=stage,
        run_identity=spec.identity,
        family=spec.model_family,
        category=spec.category,
        seed=spec.seed,
        dataset_manifest_sha256=cast(str, spec.dataset_manifest_sha256),
        code_revision=cast(str, record.code_revision),
        config_sha256=config.identity,
        environment_lock_sha256=cast(str, record.environment_lock_sha256),
        model_revision=cast(str, record.model_revision),
        checkpoint_sha256=fit.checkpoint.sha256,
        threshold_artifact_sha256=sha256_file(threshold_path),
        prediction_artifact_sha256=sha256_file(prediction_path),
        prediction_locator=prediction_path.relative_to(store.root).as_posix(),
        run_record_sha256=sha256_file(run_dir / "record.json"),
        metrics=metrics,
    )
    _write_identity_contract(evidence_path, evidence)
    del adapter
    gc.collect()
    torch.cuda.empty_cache()
    return evidence


def _git_revision(repository: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise PublicGateError("formal public evaluation requires a clean Git worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _path_argument(value: Path | None, environment_name: str) -> Path:
    if value is not None:
        return value.expanduser().resolve()
    environment_value = os.environ.get(environment_name)
    if not environment_value:
        raise PublicGateError(f"{environment_name} is required")
    return Path(environment_value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the frozen public benchmark")
    parser.add_argument("--stage", required=True, choices=("screening", "replication"))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--experiment-version", default="mvtec-ad2-v1")
    parser.add_argument("--imagenette-root", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--gpu-lock", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = Path.cwd().resolve()
    revision = _git_revision(repository)
    if not args.device.startswith("cuda:"):
        raise PublicGateError("formal public benchmark requires an indexed CUDA device")
    data_root = _path_argument(args.data_root, "MVTECAD2_DATA_ROOT").resolve(strict=True)
    runs_root = _path_argument(args.runs_root, "MVTECAD2_RUNS_ROOT")
    if runs_root == repository or runs_root.is_relative_to(repository):
        raise PublicGateError("runs root must remain outside the repository")
    dataset_manifest = (
        args.dataset_manifest.expanduser().resolve(strict=True)
        if args.dataset_manifest is not None
        else data_root.parent / f"{data_root.name}.manifest.json"
    )
    stage_name = cast(Literal["screening", "replication"], args.stage)
    queue_path = (
        args.queue.expanduser().resolve(strict=True)
        if args.queue is not None
        else runs_root / f"queue-{stage_name}.json"
    )
    stage, specs = _load_frozen_queue(queue_path, stage_name)
    manifest = load_dataset_manifest(dataset_manifest)
    if stage.dataset_manifest_sha256 != manifest.identity:
        raise PublicGateError("frozen queue dataset identity mismatch")
    store = RunStore(runs_root)
    evidence_root = runs_root / "evidence"
    stage_path = evidence_root / "screening-stage.json"
    gate_path = evidence_root / "public-gate.json"
    if stage_name == "screening":
        frozen = freeze_screening_stage(
            store,
            specs,
            experiment_version=args.experiment_version,
        )
        write_frozen_stage(stage_path, frozen)
        gate = open_public_gate(stage_path, gate_path)
    else:
        gate = verify_public_gate(stage_path, gate_path)
        if any(store.inspect(spec) != "completed" for spec in specs):
            raise PublicGateError("replication public evaluation requires all 32 completed runs")
    if gate.experiment_version != args.experiment_version:
        raise PublicGateError("requested experiment version differs from public gate")

    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else evidence_root / "public_benchmark.json"
    )
    previous_runs: tuple[BenchmarkRunEvidence, ...] = ()
    if output_path.exists():
        previous = load_public_benchmark(output_path)
        previous_runs = previous.runs
    evaluation_root = runs_root / "public-evaluation"
    imagenette_root = (
        args.imagenette_root.expanduser().resolve(strict=True)
        if args.imagenette_root is not None
        else (
            Path(os.environ["MVTECAD2_IMAGENETTE_ROOT"]).expanduser().resolve(strict=True)
            if "MVTECAD2_IMAGENETTE_ROOT" in os.environ
            else None
        )
    )
    lock_path = (
        args.gpu_lock.expanduser().resolve()
        if args.gpu_lock is not None
        else runs_root.parent / ".mvtec-ad2-gpu.lock"
    )
    repository_identity = hashlib.sha256(str(repository).encode("utf-8")).hexdigest()
    new_runs: list[BenchmarkRunEvidence] = []
    with GpuLease(lock_path, repository_identity=repository_identity).acquire(
        f"public-{stage_name}"
    ) as lease:
        for spec in specs:
            evidence = _evaluate_run(
                store=store,
                spec=spec,
                stage=stage_name,
                data_root=data_root,
                dataset_manifest=dataset_manifest,
                evaluation_root=evaluation_root,
                device=args.device,
                imagenette_root=imagenette_root,
            )
            if evidence.code_revision != revision:
                raise PublicGateError("run code revision differs from evaluation revision")
            new_runs.append(evidence)
            lease.heartbeat()
    by_identity = {run.run_identity: run for run in (*previous_runs, *new_runs)}
    benchmark = PublicBenchmark(
        experiment_version=args.experiment_version,
        dataset_manifest_sha256=manifest.identity,
        public_gate_identity=gate.identity,
        runs=tuple(
            sorted(
                by_identity.values(),
                key=lambda run: (run.category, run.family, run.seed),
            )
        ),
    )
    write_public_benchmark(output_path, benchmark)
    print(
        json.dumps(
            {
                "benchmark_sha256": benchmark.identity,
                "output": str(output_path),
                "run_count": len(benchmark.runs),
                "stage": stage_name,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
