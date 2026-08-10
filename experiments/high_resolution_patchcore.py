from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, computed_field, model_validator

from experiments.evaluate_public import (
    BenchmarkRunEvidence,
    PublicBenchmark,
    PublicRunMetrics,
    _evaluate_run,
    load_public_benchmark,
)
from experiments.models.base import ModelConfig, load_model_config
from experiments.orchestration.gpu_lock import GpuLease
from experiments.orchestration.supervisor import (
    FailureKind,
    RunStore,
    SubprocessExecutor,
    Supervisor,
)
from experiments.run_matrix import _attempt_command_factory, _git_revision
from experiments.train import load_dataset_manifest
from inspection_platform.contracts import RunSpec, canonical_hash, sha256_file
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256

STUDY_CATEGORIES: tuple[MVTecAD2Category, MVTecAD2Category] = (
    "can",
    "wallplugs",
)
BASELINE_RESOLUTION: tuple[Literal[512], Literal[512]] = (512, 512)
CANDIDATE_RESOLUTION: tuple[Literal[768], Literal[768]] = (768, 768)
STUDY_SEED = 42
StudyVerdict = Literal[
    "PROMISING",
    "MIXED",
    "NO_CLEAR_GAIN",
    "RESOURCE_LIMIT_EXCEEDED",
]


def validate_candidate_config(candidate: ModelConfig, *, baseline: ModelConfig) -> None:
    """Require the candidate to change only PatchCore input geometry."""

    if baseline.family != "patchcore" or baseline.input_size != BASELINE_RESOLUTION:
        raise ValueError("baseline must be the frozen 512 x 512 PatchCore config")
    if candidate.family != "patchcore" or candidate.input_size != CANDIDATE_RESOLUTION:
        raise ValueError("candidate must be the frozen 768 x 768 PatchCore config")

    baseline_payload = baseline.model_dump(mode="json", exclude_computed_fields=True)
    normalized_candidate = deepcopy(candidate.model_dump(mode="json", exclude_computed_fields=True))
    normalized_candidate["input_size"] = list(BASELINE_RESOLUTION)
    preprocessing = normalized_candidate.get("preprocessing")
    if not isinstance(preprocessing, dict):
        raise ValueError("candidate preprocessing must be an object")
    preprocessing["resize"] = list(BASELINE_RESOLUTION)
    if normalized_candidate != baseline_payload:
        raise ValueError(
            "high-resolution candidate may change only input_size and preprocessing.resize"
        )


def build_study_specs(
    candidate: ModelConfig,
    *,
    dataset_manifest_sha256: Sha256,
) -> tuple[RunSpec, RunSpec]:
    """Build the two deterministic public-only study runs."""

    config = candidate.model_dump(mode="json", exclude_computed_fields=True)
    can, wallplugs = (
        RunSpec(
            model_family="patchcore",
            category=category,
            seed=STUDY_SEED,
            config=dict(config),
            dataset_manifest_sha256=dataset_manifest_sha256,
        )
        for category in STUDY_CATEGORIES
    )
    return can, wallplugs


class StudyMetrics(ContractModel):
    """Aggregate public metrics retained by the research report."""

    au_pro: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    image_auroc: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    pixel_auroc: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    gpu_p95_latency_ms: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    peak_vram_mib: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    artifact_size_bytes: Annotated[int, Field(gt=0)]
    per_image_failure_rate: Annotated[float, Field(ge=0.0, le=1.0)]

    @classmethod
    def from_public_metrics(cls, metrics: PublicRunMetrics) -> StudyMetrics:
        return cls(
            au_pro=metrics.pixel.au_pro,
            image_auroc=metrics.image.auroc,
            pixel_auroc=metrics.pixel.auroc,
            gpu_p95_latency_ms=metrics.gpu_latency.p95_ms,
            peak_vram_mib=metrics.peak_vram_mib,
            artifact_size_bytes=metrics.artifact_size_bytes,
            per_image_failure_rate=metrics.per_image_failure_rate,
        )


class StudyComparison(ContractModel):
    category: MVTecAD2Category
    baseline_run_identity: Sha256
    candidate_run_identity: Sha256
    baseline: StudyMetrics
    candidate: StudyMetrics
    au_pro_delta: Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]
    image_auroc_delta: Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]
    pixel_auroc_delta: Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]
    candidate_duration_seconds: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def require_exact_deltas(self) -> Self:
        expected = (
            self.candidate.au_pro - self.baseline.au_pro,
            self.candidate.image_auroc - self.baseline.image_auroc,
            self.candidate.pixel_auroc - self.baseline.pixel_auroc,
        )
        observed = (self.au_pro_delta, self.image_auroc_delta, self.pixel_auroc_delta)
        if any(
            abs(actual - wanted) > 1e-12 for actual, wanted in zip(observed, expected, strict=True)
        ):
            raise ValueError("study comparison deltas differ from aggregate metrics")
        return self


def build_comparison(
    *,
    category: MVTecAD2Category | str,
    baseline_run_identity: Sha256,
    candidate_run_identity: Sha256,
    baseline: StudyMetrics,
    candidate: StudyMetrics,
    candidate_duration_seconds: float,
) -> StudyComparison:
    return StudyComparison(
        category=cast(MVTecAD2Category, category),
        baseline_run_identity=baseline_run_identity,
        candidate_run_identity=candidate_run_identity,
        baseline=baseline,
        candidate=candidate,
        au_pro_delta=candidate.au_pro - baseline.au_pro,
        image_auroc_delta=candidate.image_auroc - baseline.image_auroc,
        pixel_auroc_delta=candidate.pixel_auroc - baseline.pixel_auroc,
        candidate_duration_seconds=candidate_duration_seconds,
    )


class StudyFailure(ContractModel):
    """Sanitized aggregate evidence for a candidate run that could not complete."""

    category: MVTecAD2Category
    candidate_run_identity: Sha256
    code_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    candidate_duration_seconds: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    attempt: Annotated[int, Field(gt=0)]
    exit_code: int
    error_kind: FailureKind
    error_sha256: Sha256

    @model_validator(mode="after")
    def require_failure_exit_code(self) -> Self:
        if self.exit_code == 0:
            raise ValueError("failed study run must have a nonzero exit code")
        return self


def classify_study(comparisons: tuple[StudyComparison, StudyComparison]) -> StudyVerdict:
    if any(
        item.candidate.peak_vram_mib > 12_288.0
        or item.candidate.gpu_p95_latency_ms > 500.0
        or item.candidate.per_image_failure_rate != 0.0
        for item in comparisons
    ):
        return "RESOURCE_LIMIT_EXCEEDED"
    gains = tuple(item.au_pro_delta for item in comparisons)
    if max(gains) >= 0.02:
        return "MIXED" if min(gains) < -0.02 else "PROMISING"
    return "NO_CLEAR_GAIN"


def select_baseline_runs(
    benchmark: PublicBenchmark,
    *,
    baseline_config: ModelConfig,
) -> dict[MVTecAD2Category, BenchmarkRunEvidence]:
    if baseline_config.family != "patchcore" or baseline_config.input_size != BASELINE_RESOLUTION:
        raise ValueError("baseline must be the frozen 512 x 512 PatchCore config")
    selected: dict[MVTecAD2Category, BenchmarkRunEvidence] = {}
    for category in STUDY_CATEGORIES:
        matches = [
            run
            for run in benchmark.runs
            if run.stage == "screening"
            and run.category == category
            and run.family == "patchcore"
            and run.seed == STUDY_SEED
            and run.config_sha256 == baseline_config.identity
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one frozen PatchCore baseline for {category}")
        selected[category] = matches[0]
    return selected


def validate_external_paths(*, repository: Path, runs_root: Path, output: Path) -> None:
    repo = repository.expanduser().resolve(strict=True)
    runs = runs_root.expanduser().resolve()
    destination = output.expanduser().resolve()
    if runs == repo or runs.is_relative_to(repo):
        raise ValueError("research runs root must be outside the repository")
    if destination == runs or not destination.is_relative_to(runs):
        raise ValueError("research report must be inside the runs root")


class HighResolutionStudyReport(ContractModel):
    study: Literal["patchcore-512-vs-768-can-wallplugs-seed42"] = (
        "patchcore-512-vs-768-can-wallplugs-seed42"
    )
    scope: Literal["test_public-only"] = "test_public-only"
    submitted: Literal[False] = False
    source_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    dataset_manifest_sha256: Sha256
    baseline_benchmark_sha256: Sha256
    baseline_config_sha256: Sha256
    candidate_config_sha256: Sha256
    seed: Literal[42] = 42
    baseline_resolution: tuple[Literal[512], Literal[512]] = BASELINE_RESOLUTION
    candidate_resolution: tuple[Literal[768], Literal[768]] = CANDIDATE_RESOLUTION
    evaluation_size: tuple[Literal[256], Literal[256]] = (256, 256)
    comparisons: tuple[StudyComparison, ...] = ()
    failures: tuple[StudyFailure, ...] = ()
    verdict: StudyVerdict

    @model_validator(mode="after")
    def require_fixed_complete_study(self) -> Self:
        comparison_categories = tuple(item.category for item in self.comparisons)
        failure_categories = tuple(item.category for item in self.failures)
        observed = (*comparison_categories, *failure_categories)
        categories = tuple(category for category in STUDY_CATEGORIES if category in observed)
        if categories != STUDY_CATEGORIES or len(observed) != len(set(observed)):
            raise ValueError("study report must contain one outcome for can and wallplugs")
        expected = (
            "RESOURCE_LIMIT_EXCEEDED"
            if self.failures
            else classify_study(cast(tuple[StudyComparison, StudyComparison], self.comparisons))
        )
        if self.verdict != expected:
            raise ValueError("study verdict differs from frozen classification rules")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


def write_study_report(path: Path, report: HighResolutionStudyReport) -> Path:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = report.identity
    if destination.exists():
        if json.loads(destination.read_text(encoding="utf-8")) != payload:
            raise ValueError("existing high-resolution study report differs")
        return destination
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed public-only high-resolution PatchCore study"
    )
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--candidate-config", required=True, type=Path)
    parser.add_argument(
        "--baseline-config",
        type=Path,
        default=Path("experiments/configs/models/patchcore.yaml"),
    )
    parser.add_argument(
        "--baseline-public-benchmark",
        type=Path,
        default=Path("reports/public_benchmark.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--gpu-lock", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _study_report(
    *,
    source_sha: str,
    manifest_sha256: Sha256,
    baseline_benchmark: PublicBenchmark,
    baseline_config: ModelConfig,
    candidate_config: ModelConfig,
    baselines: dict[MVTecAD2Category, BenchmarkRunEvidence],
    candidates: dict[MVTecAD2Category, BenchmarkRunEvidence],
    failures: dict[MVTecAD2Category, StudyFailure],
    durations: dict[MVTecAD2Category, float],
) -> HighResolutionStudyReport:
    comparisons = tuple(
        build_comparison(
            category=category,
            baseline_run_identity=baselines[category].run_identity,
            candidate_run_identity=candidates[category].run_identity,
            baseline=StudyMetrics.from_public_metrics(baselines[category].metrics),
            candidate=StudyMetrics.from_public_metrics(candidates[category].metrics),
            candidate_duration_seconds=durations[category],
        )
        for category in STUDY_CATEGORIES
        if category in candidates
    )
    checked_failures = tuple(
        failures[category] for category in STUDY_CATEGORIES if category in failures
    )
    verdict: StudyVerdict = (
        "RESOURCE_LIMIT_EXCEEDED"
        if checked_failures
        else classify_study(cast(tuple[StudyComparison, StudyComparison], comparisons))
    )
    return HighResolutionStudyReport(
        source_sha=source_sha,
        dataset_manifest_sha256=manifest_sha256,
        baseline_benchmark_sha256=baseline_benchmark.identity,
        baseline_config_sha256=baseline_config.identity,
        candidate_config_sha256=candidate_config.identity,
        comparisons=comparisons,
        failures=checked_failures,
        verdict=verdict,
    )


def _failure_evidence(*, store: RunStore, spec: RunSpec, duration_seconds: float) -> StudyFailure:
    run_dir = store.run_dir(spec)
    record = store.load_record(run_dir)
    result_path = run_dir / "worker-result.json"
    if not result_path.is_file():
        raise ValueError("failed study run lacks worker-result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    error_kind = result.get("error_kind")
    allowed_kinds: set[str] = {
        "oom",
        "checksum_mismatch",
        "non_finite",
        "invalid_shape",
        "corrupt_checkpoint",
        "subprocess",
    }
    if error_kind not in allowed_kinds:
        raise ValueError("failed study run has an unsupported error kind")
    if record.exit_code is None or record.error is None:
        raise ValueError("failed study run lacks exit code or error evidence")
    return StudyFailure(
        category=spec.category,
        candidate_run_identity=spec.identity,
        code_revision=record.code_revision,
        candidate_duration_seconds=duration_seconds,
        attempt=record.attempt,
        exit_code=record.exit_code,
        error_kind=cast(FailureKind, error_kind),
        error_sha256=hashlib.sha256(record.error.encode("utf-8")).hexdigest(),
    )


def execute_formal_study(args: argparse.Namespace) -> HighResolutionStudyReport | None:
    repository = Path.cwd().resolve(strict=True)
    data_root = args.data_root.expanduser().resolve(strict=True)
    manifest_path = args.dataset_manifest.expanduser().resolve(strict=True)
    runs_root = args.runs_root.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else runs_root / "evidence" / "high-resolution-patchcore.json"
    )
    validate_external_paths(repository=repository, runs_root=runs_root, output=output)

    baseline_config = load_model_config(args.baseline_config)
    candidate_config = load_model_config(args.candidate_config)
    validate_candidate_config(candidate_config, baseline=baseline_config)
    manifest = load_dataset_manifest(manifest_path)
    baseline_benchmark = load_public_benchmark(args.baseline_public_benchmark)
    if baseline_benchmark.dataset_manifest_sha256 != manifest.identity:
        raise ValueError("baseline public benchmark dataset identity mismatch")
    baselines = select_baseline_runs(baseline_benchmark, baseline_config=baseline_config)
    specs = build_study_specs(candidate_config, dataset_manifest_sha256=manifest.identity)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "baseline_config_sha256": baseline_config.identity,
                    "candidate_config_sha256": candidate_config.identity,
                    "categories": list(STUDY_CATEGORIES),
                    "count": len(specs),
                    "identities": [spec.identity for spec in specs],
                    "seed": STUDY_SEED,
                },
                sort_keys=True,
            )
        )
        return None

    revision = _git_revision(repository)
    environment_lock_sha256 = sha256_file(repository / "uv.lock")
    lock_path = (
        args.gpu_lock.expanduser().resolve()
        if args.gpu_lock is not None
        else runs_root.parent / ".mvtec-ad2-gpu.lock"
    )
    repository_identity = hashlib.sha256(str(repository).encode("utf-8")).hexdigest()
    store = RunStore(runs_root)
    supervisor = Supervisor(
        store,
        runner=SubprocessExecutor(
            _attempt_command_factory(
                data_root=data_root,
                dataset_manifest=manifest_path,
                device=args.device,
                imagenette_root=None,
            )
        ),
        gpu_lease=GpuLease(lock_path, repository_identity=repository_identity),
        code_revision=revision,
        environment_lock_sha256=environment_lock_sha256,
        model_revision=lambda spec: (
            f"anomalib:{spec.config.get('anomalib_version')}/"
            f"{spec.config.get('model_name')}/{spec.config.get('backbone')}"
        ),
    )
    summaries = tuple(supervisor.run((spec,)) for spec in specs)

    candidates: dict[MVTecAD2Category, BenchmarkRunEvidence] = {}
    evaluation_root = runs_root / "public-evaluation"
    completed_specs = tuple(
        spec
        for spec, summary in zip(specs, summaries, strict=True)
        if spec.identity in (*summary.completed, *summary.skipped)
    )
    if completed_specs:
        with GpuLease(lock_path, repository_identity=repository_identity).acquire(
            "high-resolution-patchcore-public"
        ) as lease:
            for spec in completed_specs:
                candidate = _evaluate_run(
                    store=store,
                    spec=spec,
                    stage="screening",
                    data_root=data_root,
                    dataset_manifest=manifest_path,
                    evaluation_root=evaluation_root,
                    device=args.device,
                    imagenette_root=None,
                )
                if candidate.code_revision != revision:
                    raise ValueError("candidate run code revision differs from study source")
                candidates[spec.category] = candidate
                lease.heartbeat()

    durations: dict[MVTecAD2Category, float] = {}
    failures: dict[MVTecAD2Category, StudyFailure] = {}
    for spec in specs:
        record = store.load_record(store.run_dir(spec))
        if record.started_at is None or record.finished_at is None:
            raise ValueError("study run lacks wall-clock timestamps")
        duration = record.finished_at - record.started_at
        if duration <= 0 or not math.isfinite(duration):
            raise ValueError("study run has invalid wall-clock duration")
        durations[spec.category] = duration
        if record.status != "completed":
            failures[spec.category] = _failure_evidence(
                store=store, spec=spec, duration_seconds=duration
            )

    report = _study_report(
        source_sha=revision,
        manifest_sha256=manifest.identity,
        baseline_benchmark=baseline_benchmark,
        baseline_config=baseline_config,
        candidate_config=candidate_config,
        baselines=baselines,
        candidates=candidates,
        failures=failures,
        durations=durations,
    )
    write_study_report(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    report = execute_formal_study(build_parser().parse_args(argv))
    if report is not None:
        print(
            json.dumps(
                {
                    "report_sha256": report.identity,
                    "status": report.verdict,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
