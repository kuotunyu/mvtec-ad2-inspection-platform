from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from copy import deepcopy
from pathlib import Path
from statistics import fmean
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
    StudyMetrics,
    build_comparison,
    validate_external_paths,
)
from experiments.models.base import ModelConfig, load_model_config
from experiments.orchestration.gpu_lock import GpuLease
from experiments.orchestration.supervisor import RunStore, SubprocessExecutor, Supervisor
from experiments.patchcore_resolution_frontier import FrontierReport
from experiments.run_matrix import _attempt_command_factory, _git_revision
from experiments.train import load_dataset_manifest
from inspection_platform.contracts import RunSpec, canonical_hash, sha256_file
from inspection_platform.contracts._base import ContractModel
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


def select_followup_specs(
    specs: tuple[RunSpec, ...], *, probe: StudyComparison
) -> tuple[RunSpec, ...]:
    if len(specs) != 5:
        raise ValueError("balanced study requires exactly five ordered candidate specs")
    return specs[3:] if passes_stage_b_advance(probe) else ()


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


def select_wallplugs_baselines(
    benchmark: PublicBenchmark, *, baseline_config: ModelConfig
) -> dict[int, BenchmarkRunEvidence]:
    if baseline_config.family != "patchcore" or baseline_config.input_size != BASELINE_RESOLUTION:
        raise ValueError("baseline must be the frozen 512 x 512 PatchCore config")
    selected: dict[int, BenchmarkRunEvidence] = {}
    for seed in (42, 17, 2026):
        matches = [
            run
            for run in benchmark.runs
            if run.category == CATEGORY
            and run.family == "patchcore"
            and run.seed == seed
            and run.config_sha256 == baseline_config.identity
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one frozen wallplugs PatchCore baseline for seed {seed}")
        selected[seed] = matches[0]
    return selected


class BalancedStudyReport(ContractModel):
    study: Literal["balanced-patchcore-wallplugs"] = "balanced-patchcore-wallplugs"
    scope: Literal["test_public-only"] = "test_public-only"
    submitted: Literal[False] = False
    source_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    dataset_manifest_sha256: Sha256
    baseline_benchmark_sha256: Sha256
    baseline_config_sha256: Sha256
    config_640_sha256: Sha256
    config_576_sha256: Sha256
    frontier_report_sha256: Sha256
    stage_a_comparisons: tuple[StudyComparison, StudyComparison, StudyComparison]
    stage_a_verdict: StageAVerdict
    stage_b_comparisons: tuple[StudyComparison, ...]
    stage_b_advanced: bool
    stage_b_verdict: StageBVerdict

    @model_validator(mode="after")
    def require_frozen_outcomes(self) -> Self:
        expected_a = classify_stage_a(self.stage_a_comparisons)
        if self.stage_a_verdict != expected_a:
            raise ValueError("stage A verdict differs from frozen classification rules")
        if len(self.stage_b_comparisons) not in (1, 3):
            raise ValueError("stage B must contain one probe or three replicated comparisons")
        advance = passes_stage_b_advance(self.stage_b_comparisons[0])
        if self.stage_b_advanced != advance:
            raise ValueError("stage B advance flag differs from the seed-42 gate")
        if advance != (len(self.stage_b_comparisons) == 3):
            raise ValueError("stage B replication count differs from the advance decision")
        expected_b: StageBVerdict
        if len(self.stage_b_comparisons) == 3:
            expected_b = classify_stage_b(
                (
                    self.stage_b_comparisons[0],
                    self.stage_b_comparisons[1],
                    self.stage_b_comparisons[2],
                )
            )
        elif self.stage_b_comparisons[0].au_pro_delta >= 0.02:
            expected_b = "MIXED"
        else:
            expected_b = "NO_CLEAR_GAIN"
        if self.stage_b_verdict != expected_b:
            raise ValueError("stage B verdict differs from frozen classification rules")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


def write_balanced_report(path: Path, report: BalancedStudyReport) -> Path:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = report.identity
    if destination.exists():
        if json.loads(destination.read_text(encoding="utf-8")) != payload:
            raise ValueError("existing balanced study report differs")
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


def _load_frontier_report(path: Path) -> FrontierReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    claimed = payload.pop("canonical_sha256", None)
    report = FrontierReport.model_validate(payload)
    if claimed != report.identity:
        raise ValueError("frontier report identity mismatch")
    if report.comparison is None or report.failure is not None:
        raise ValueError("balanced study requires the completed 640 seed-42 frontier")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the balanced public-only PatchCore study")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--config-640", required=True, type=Path)
    parser.add_argument("--config-576", required=True, type=Path)
    parser.add_argument(
        "--baseline-config", type=Path, default=Path("experiments/configs/models/patchcore.yaml")
    )
    parser.add_argument(
        "--baseline-public-benchmark", type=Path, default=Path("reports/public_benchmark.json")
    )
    parser.add_argument(
        "--frontier-report", type=Path, default=Path("reports/patchcore_resolution_frontier.json")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--gpu-lock", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def execute_balanced_study(args: argparse.Namespace) -> BalancedStudyReport | None:
    repository = Path.cwd().resolve(strict=True)
    data_root = args.data_root.expanduser().resolve(strict=True)
    manifest_path = args.dataset_manifest.expanduser().resolve(strict=True)
    runs_root = args.runs_root.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else runs_root / "evidence" / "balanced-patchcore-study.json"
    )
    validate_external_paths(repository=repository, runs_root=runs_root, output=output)
    baseline_config = load_model_config(args.baseline_config)
    config_640 = load_model_config(args.config_640)
    config_576 = load_model_config(args.config_576)
    validate_balanced_config(config_640, baseline=baseline_config, resolution=(640, 640))
    validate_balanced_config(config_576, baseline=baseline_config, resolution=(576, 576))
    manifest = load_dataset_manifest(manifest_path)
    benchmark = load_public_benchmark(args.baseline_public_benchmark)
    if benchmark.dataset_manifest_sha256 != manifest.identity:
        raise ValueError("baseline public benchmark dataset identity mismatch")
    baselines = select_wallplugs_baselines(benchmark, baseline_config=baseline_config)
    frontier = _load_frontier_report(args.frontier_report)
    frontier_comparison = frontier.comparison
    if frontier_comparison is None:
        raise ValueError("frontier report lacks its completed comparison")
    if frontier.dataset_manifest_sha256 != manifest.identity:
        raise ValueError("frontier dataset identity mismatch")
    specs = build_candidate_specs(config_640, config_576, dataset_manifest_sha256=manifest.identity)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "config_576_sha256": config_576.identity,
                    "config_640_sha256": config_640.identity,
                    "dataset_manifest_sha256": manifest.identity,
                    "identities": [spec.identity for spec in specs],
                    "ordered_candidates": [
                        [spec.seed, spec.config["input_size"]] for spec in specs
                    ],
                    "stage_b_rule": "replicate-17-2026-only-if-seed42-balanced",
                },
                sort_keys=True,
            )
        )
        return None

    revision = _git_revision(repository)
    lock_path = (
        args.gpu_lock.expanduser().resolve()
        if args.gpu_lock is not None
        else runs_root.parent / ".mvtec-ad2-gpu.lock"
    )
    repository_identity = hashlib.sha256(str(repository).encode()).hexdigest()
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
        environment_lock_sha256=sha256_file(repository / "uv.lock"),
        model_revision=lambda item: (
            f"anomalib:{item.config.get('anomalib_version')}/"
            f"{item.config.get('model_name')}/{item.config.get('backbone')}"
        ),
    )

    def run_candidate(spec: RunSpec) -> StudyComparison:
        summary = supervisor.run((spec,))
        if spec.identity not in (*summary.completed, *summary.skipped):
            raise RuntimeError(f"candidate failed with preserved evidence: {spec.identity}")
        record = store.load_record(store.run_dir(spec))
        if record.started_at is None or record.finished_at is None:
            raise ValueError("candidate run lacks timestamps")
        duration = record.finished_at - record.started_at
        if duration <= 0 or not math.isfinite(duration):
            raise ValueError("candidate run duration is invalid")
        with GpuLease(lock_path, repository_identity=repository_identity).acquire(
            "balanced-patchcore-public"
        ):
            candidate = _evaluate_run(
                store=store,
                spec=spec,
                stage="replication" if spec.seed != 42 else "screening",
                data_root=data_root,
                dataset_manifest=manifest_path,
                evaluation_root=runs_root / "public-evaluation",
                device=args.device,
                imagenette_root=None,
            )
        if candidate.code_revision != revision:
            raise ValueError("candidate source revision mismatch")
        baseline = baselines[spec.seed]
        return build_comparison(
            category=CATEGORY,
            baseline_run_identity=baseline.run_identity,
            candidate_run_identity=candidate.run_identity,
            baseline=StudyMetrics.from_public_metrics(baseline.metrics),
            candidate=StudyMetrics.from_public_metrics(candidate.metrics),
            candidate_duration_seconds=duration,
        )

    stage_a = (frontier_comparison, run_candidate(specs[0]), run_candidate(specs[1]))
    probe = run_candidate(specs[2])
    followups = select_followup_specs(specs, probe=probe)
    stage_b = (probe, *(run_candidate(spec) for spec in followups))
    advanced = bool(followups)
    stage_b_verdict: StageBVerdict
    if advanced:
        stage_b_verdict = classify_stage_b((stage_b[0], stage_b[1], stage_b[2]))
    elif probe.au_pro_delta >= 0.02:
        stage_b_verdict = "MIXED"
    else:
        stage_b_verdict = "NO_CLEAR_GAIN"
    report = BalancedStudyReport(
        source_sha=revision,
        dataset_manifest_sha256=manifest.identity,
        baseline_benchmark_sha256=benchmark.identity,
        baseline_config_sha256=baseline_config.identity,
        config_640_sha256=config_640.identity,
        config_576_sha256=config_576.identity,
        frontier_report_sha256=frontier.identity,
        stage_a_comparisons=stage_a,
        stage_a_verdict=classify_stage_a(stage_a),
        stage_b_comparisons=stage_b,
        stage_b_advanced=advanced,
        stage_b_verdict=stage_b_verdict,
    )
    write_balanced_report(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    report = execute_balanced_study(build_parser().parse_args(argv))
    if report is not None:
        print(json.dumps({"report_sha256": report.identity, "status": report.stage_b_verdict}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
