from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, computed_field, model_validator

from experiments.evaluate_public import (
    BenchmarkRunEvidence,
    PublicBenchmark,
    _evaluate_run,
    load_public_benchmark,
)
from experiments.high_resolution_patchcore import (
    StudyComparison,
    StudyFailure,
    StudyMetrics,
    _failure_evidence,
    build_comparison,
    validate_external_paths,
)
from experiments.models.base import ModelConfig, load_model_config
from experiments.orchestration.gpu_lock import GpuLease
from experiments.orchestration.supervisor import RunStore, SubprocessExecutor, Supervisor
from experiments.run_matrix import _attempt_command_factory, _git_revision
from experiments.train import load_dataset_manifest
from inspection_platform.contracts import RunSpec, canonical_hash, sha256_file
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import Sha256

BASELINE_RESOLUTION: tuple[Literal[512], Literal[512]] = (512, 512)
CANDIDATE_RESOLUTION: tuple[Literal[640], Literal[640]] = (640, 640)
CATEGORY: Literal["wallplugs"] = "wallplugs"
STUDY_SEED: Literal[42] = 42
FrontierVerdict = Literal[
    "PROMISING",
    "NO_CLEAR_GAIN",
    "REGRESSION",
    "RESOURCE_LIMIT_EXCEEDED",
]


def validate_frontier_config(candidate: ModelConfig, *, baseline: ModelConfig) -> None:
    if baseline.family != "patchcore" or baseline.input_size != BASELINE_RESOLUTION:
        raise ValueError("baseline must be the frozen 512 x 512 PatchCore config")
    if candidate.family != "patchcore" or candidate.input_size != CANDIDATE_RESOLUTION:
        raise ValueError("candidate must be the frozen 640 x 640 PatchCore config")

    baseline_payload = baseline.model_dump(mode="json", exclude_computed_fields=True)
    normalized = deepcopy(candidate.model_dump(mode="json", exclude_computed_fields=True))
    normalized["input_size"] = list(BASELINE_RESOLUTION)
    preprocessing = normalized.get("preprocessing")
    if not isinstance(preprocessing, dict):
        raise ValueError("candidate preprocessing must be an object")
    preprocessing["resize"] = list(BASELINE_RESOLUTION)
    if normalized != baseline_payload:
        raise ValueError("candidate may change only input_size and preprocessing.resize")


def build_frontier_spec(candidate: ModelConfig, *, dataset_manifest_sha256: Sha256) -> RunSpec:
    return RunSpec(
        model_family="patchcore",
        category=CATEGORY,
        seed=STUDY_SEED,
        config=candidate.model_dump(mode="json", exclude_computed_fields=True),
        dataset_manifest_sha256=dataset_manifest_sha256,
    )


def select_wallplugs_baseline(
    benchmark: PublicBenchmark, *, baseline_config: ModelConfig
) -> BenchmarkRunEvidence:
    if baseline_config.family != "patchcore" or baseline_config.input_size != BASELINE_RESOLUTION:
        raise ValueError("baseline must be the frozen 512 x 512 PatchCore config")
    matches = [
        run
        for run in benchmark.runs
        if run.stage == "screening"
        and run.category == CATEGORY
        and run.family == "patchcore"
        and run.seed == STUDY_SEED
        and run.config_sha256 == baseline_config.identity
    ]
    if len(matches) != 1:
        raise ValueError("expected one frozen PatchCore baseline for wallplugs")
    return matches[0]


def classify_frontier(
    comparison: StudyComparison | None, *, failed: bool = False
) -> FrontierVerdict:
    if failed or comparison is None:
        return "RESOURCE_LIMIT_EXCEEDED"
    if (
        comparison.candidate.peak_vram_mib > 12_288.0
        or comparison.candidate.gpu_p95_latency_ms > 500.0
        or comparison.candidate.per_image_failure_rate != 0.0
    ):
        return "RESOURCE_LIMIT_EXCEEDED"
    if comparison.au_pro_delta >= 0.02:
        return "PROMISING"
    if comparison.au_pro_delta < -0.02:
        return "REGRESSION"
    return "NO_CLEAR_GAIN"


class FrontierReport(ContractModel):
    study: Literal["patchcore-512-vs-640-wallplugs-seed42"] = (
        "patchcore-512-vs-640-wallplugs-seed42"
    )
    scope: Literal["test_public-only"] = "test_public-only"
    submitted: Literal[False] = False
    source_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    dataset_manifest_sha256: Sha256
    baseline_benchmark_sha256: Sha256
    baseline_config_sha256: Sha256
    candidate_config_sha256: Sha256
    seed: Literal[42] = 42
    category: Literal["wallplugs"] = CATEGORY
    baseline_resolution: tuple[Literal[512], Literal[512]] = BASELINE_RESOLUTION
    candidate_resolution: tuple[Literal[640], Literal[640]] = CANDIDATE_RESOLUTION
    evaluation_size: tuple[Literal[256], Literal[256]] = (256, 256)
    candidate_training_peak_vram_mib: (
        Annotated[float, Field(gt=0.0, allow_inf_nan=False)] | None
    ) = None
    comparison: StudyComparison | None = None
    failure: StudyFailure | None = None
    verdict: FrontierVerdict

    @model_validator(mode="after")
    def require_one_outcome_and_verdict(self) -> Self:
        if (self.comparison is None) == (self.failure is None):
            raise ValueError("frontier report must contain exactly one outcome")
        if self.comparison is not None:
            if self.comparison.category != CATEGORY:
                raise ValueError("frontier comparison must be for wallplugs")
            if self.candidate_training_peak_vram_mib is None:
                raise ValueError("completed frontier run requires training peak VRAM")
        if self.failure is not None and self.failure.category != CATEGORY:
            raise ValueError("frontier failure must be for wallplugs")
        expected = classify_frontier(self.comparison, failed=self.failure is not None)
        if self.verdict != expected:
            raise ValueError("frontier verdict differs from frozen classification rules")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


def write_frontier_report(path: Path, report: FrontierReport) -> Path:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = report.identity
    if destination.exists():
        if json.loads(destination.read_text(encoding="utf-8")) != payload:
            raise ValueError("existing frontier report differs")
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
        description="Run the fixed public-only PatchCore resolution-frontier study"
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


def execute_frontier(args: argparse.Namespace) -> FrontierReport | None:
    repository = Path.cwd().resolve(strict=True)
    data_root = args.data_root.expanduser().resolve(strict=True)
    manifest_path = args.dataset_manifest.expanduser().resolve(strict=True)
    runs_root = args.runs_root.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else runs_root / "evidence" / "patchcore-resolution-frontier.json"
    )
    validate_external_paths(repository=repository, runs_root=runs_root, output=output)

    baseline_config = load_model_config(args.baseline_config)
    candidate_config = load_model_config(args.candidate_config)
    validate_frontier_config(candidate_config, baseline=baseline_config)
    manifest = load_dataset_manifest(manifest_path)
    benchmark = load_public_benchmark(args.baseline_public_benchmark)
    if benchmark.dataset_manifest_sha256 != manifest.identity:
        raise ValueError("baseline public benchmark dataset identity mismatch")
    baseline = select_wallplugs_baseline(benchmark, baseline_config=baseline_config)
    spec = build_frontier_spec(candidate_config, dataset_manifest_sha256=manifest.identity)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "baseline_config_sha256": baseline_config.identity,
                    "candidate_config_sha256": candidate_config.identity,
                    "category": CATEGORY,
                    "identity": spec.identity,
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
        model_revision=lambda item: (
            f"anomalib:{item.config.get('anomalib_version')}/"
            f"{item.config.get('model_name')}/{item.config.get('backbone')}"
        ),
    )
    summary = supervisor.run((spec,))

    record = store.load_record(store.run_dir(spec))
    if record.started_at is None or record.finished_at is None:
        raise ValueError("frontier run lacks wall-clock timestamps")
    duration = record.finished_at - record.started_at
    if duration <= 0 or not math.isfinite(duration):
        raise ValueError("frontier run has invalid wall-clock duration")

    comparison: StudyComparison | None = None
    failure: StudyFailure | None = None
    if spec.identity in (*summary.completed, *summary.skipped):
        with GpuLease(lock_path, repository_identity=repository_identity).acquire(
            "patchcore-resolution-frontier-public"
        ):
            candidate = _evaluate_run(
                store=store,
                spec=spec,
                stage="screening",
                data_root=data_root,
                dataset_manifest=manifest_path,
                evaluation_root=runs_root / "public-evaluation",
                device=args.device,
                imagenette_root=None,
            )
        if candidate.code_revision != revision:
            raise ValueError("candidate run code revision differs from study source")
        comparison = build_comparison(
            category=CATEGORY,
            baseline_run_identity=baseline.run_identity,
            candidate_run_identity=candidate.run_identity,
            baseline=StudyMetrics.from_public_metrics(baseline.metrics),
            candidate=StudyMetrics.from_public_metrics(candidate.metrics),
            candidate_duration_seconds=duration,
        )
    else:
        failure = _failure_evidence(store=store, spec=spec, duration_seconds=duration)

    report = FrontierReport(
        source_sha=revision,
        dataset_manifest_sha256=manifest.identity,
        baseline_benchmark_sha256=benchmark.identity,
        baseline_config_sha256=baseline_config.identity,
        candidate_config_sha256=candidate_config.identity,
        candidate_training_peak_vram_mib=record.peak_vram_mib,
        comparison=comparison,
        failure=failure,
        verdict=classify_frontier(comparison, failed=failure is not None),
    )
    write_frontier_report(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    report = execute_frontier(build_parser().parse_args(argv))
    if report is not None:
        print(json.dumps({"report_sha256": report.identity, "status": report.verdict}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
