from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from statistics import fmean
from typing import Annotated, Any, Literal, Self, cast

from pydantic import Field, computed_field, model_validator

from experiments.balanced_patchcore_study import select_wallplugs_baselines
from experiments.evaluate_public import _evaluate_run, load_public_benchmark
from experiments.high_resolution_patchcore import (
    StudyComparison,
    StudyMetrics,
    build_comparison,
    validate_external_paths,
)
from experiments.models.base import ModelConfig, load_model_config
from experiments.orchestration.gpu_lock import GpuLease
from experiments.orchestration.resource_guard import (
    ResourceGuard,
    ResourceLimits,
    assert_resource_preflight,
    probe_resource_snapshot,
)
from experiments.orchestration.supervisor import RunStore, SubprocessExecutor, Supervisor
from experiments.patchcore_resolution_frontier import FrontierReport
from experiments.run_matrix import _attempt_command_factory, _git_revision
from experiments.train import load_dataset_manifest
from inspection_platform.contracts import RunSpec, canonical_hash, sha256_file
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


class MemoryBoundedStudyReport(ContractModel):
    study: Literal["memory-bounded-patchcore-wallplugs"] = "memory-bounded-patchcore-wallplugs"
    scope: Literal["test_public-only"] = "test_public-only"
    submitted: Literal[False] = False
    champions_changed: Literal[False] = False
    source_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    dataset_manifest_sha256: Sha256
    baseline_benchmark_sha256: Sha256
    baseline_config_sha256: Sha256
    reference_config_sha256: Sha256
    config_001_sha256: Sha256
    config_002_sha256: Sha256
    frontier_report_sha256: Sha256
    probes: tuple[CandidateOutcome, ...]
    selected_ratio: Ratio | None
    replications: tuple[CandidateOutcome, ...]
    verdict: StudyVerdict

    @model_validator(mode="after")
    def require_frozen_branch_and_verdict(self) -> Self:
        if len(self.probes) not in (1, 2):
            raise ValueError("study report requires one or two ordered probes")
        if tuple(item.ratio for item in self.probes) != RATIOS[: len(self.probes)]:
            raise ValueError("study probes differ from the frozen ratio order")
        if any(item.seed != 42 for item in self.probes):
            raise ValueError("study probes must use seed 42")
        first = self.probes[0]
        if len(self.probes) == 1 and first.resource_ok and not passes_seed42_gate(first):
            raise ValueError("safe ratio-0.01 quality miss requires the ratio-0.02 rescue")
        expected_ratio = select_ratio(self.probes)
        if self.selected_ratio != expected_ratio:
            raise ValueError("selected ratio differs from the frozen probe gates")

        if expected_ratio is None:
            if self.replications:
                raise ValueError("replication is forbidden without a selected ratio")
            expected_verdict: StudyVerdict = (
                "RESOURCE_LIMIT_EXCEEDED"
                if any(not item.resource_ok for item in self.probes)
                else "NO_QUALITY_PRESERVATION"
            )
        else:
            if len(self.replications) not in (1, 2):
                raise ValueError("selected ratio requires one or two ordered replication outcomes")
            if (
                tuple(item.seed for item in self.replications)
                != (17, 2026)[: len(self.replications)]
            ):
                raise ValueError("replication seeds differ from the frozen order")
            if any(item.ratio != expected_ratio for item in self.replications):
                raise ValueError("replication ratio differs from the selected ratio")
            selected_probe = next(item for item in self.probes if item.ratio == expected_ratio)
            if any(not item.resource_ok for item in self.replications):
                expected_verdict = "RESOURCE_LIMIT_EXCEEDED"
            elif len(self.replications) != 2:
                raise ValueError("resource-safe replication requires both seeds")
            else:
                expected_verdict = classify_memory_bounded_study(
                    (selected_probe, self.replications[0], self.replications[1])
                )
        if self.verdict != expected_verdict:
            raise ValueError("study verdict differs from the frozen classification")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


def write_memory_bounded_report(path: Path, report: MemoryBoundedStudyReport) -> Path:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = report.identity
    if destination.exists():
        if json.loads(destination.read_text(encoding="utf-8")) != payload:
            raise ValueError("existing memory-bounded report differs")
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


def build_dry_run_payload(
    *,
    specs: tuple[RunSpec, ...],
    source_sha: str,
    dataset_manifest_sha256: Sha256,
    reference_config_sha256: Sha256,
    config_001_sha256: Sha256,
    config_002_sha256: Sha256,
    baseline_benchmark_sha256: Sha256,
    frontier_report_sha256: Sha256,
) -> dict[str, Any]:
    return {
        "baseline_benchmark_sha256": baseline_benchmark_sha256,
        "conditional_rule": (
            "probe-0.01; rescue-0.02-only-after-safe-quality-miss; replicate-first-passing-ratio"
        ),
        "config_001_sha256": config_001_sha256,
        "config_002_sha256": config_002_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "frontier_report_sha256": frontier_report_sha256,
        "identities": [spec.identity for spec in specs],
        "ordered_candidates": [{"ratio": _spec_ratio(spec), "seed": spec.seed} for spec in specs],
        "reference_config_sha256": reference_config_sha256,
        "source_sha": source_sha,
    }


def _load_frontier_report(path: Path) -> FrontierReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    claimed = payload.pop("canonical_sha256", None)
    report = FrontierReport.model_validate(payload)
    if claimed != report.identity:
        raise ValueError("frontier report identity mismatch")
    if report.comparison is None or report.failure is not None:
        raise ValueError("memory-bounded study requires the completed 640 frontier")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run memory-bounded public PatchCore research")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--config-001", required=True, type=Path)
    parser.add_argument("--config-002", required=True, type=Path)
    parser.add_argument(
        "--reference-config",
        type=Path,
        default=Path("experiments/configs/research/patchcore-640.yaml"),
    )
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
    parser.add_argument(
        "--frontier-report",
        type=Path,
        default=Path("reports/patchcore_resolution_frontier.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--gpu-lock", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _load_existing_report(path: Path) -> MemoryBoundedStudyReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    claimed = payload.pop("canonical_sha256", None)
    report = MemoryBoundedStudyReport.model_validate(payload)
    if claimed != report.identity:
        raise ValueError("memory-bounded report identity mismatch")
    return report


def execute_memory_bounded_study(
    args: argparse.Namespace,
) -> MemoryBoundedStudyReport | None:
    repository = Path.cwd().resolve(strict=True)
    data_root = args.data_root.expanduser().resolve(strict=True)
    manifest_path = args.dataset_manifest.expanduser().resolve(strict=True)
    runs_root = args.runs_root.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else runs_root / "evidence" / "memory-bounded-patchcore.json"
    )
    validate_external_paths(repository=repository, runs_root=runs_root, output=output)
    revision = _git_revision(repository)
    reference = load_model_config(args.reference_config)
    baseline_config = load_model_config(args.baseline_config)
    config_001 = load_model_config(args.config_001)
    config_002 = load_model_config(args.config_002)
    validate_memory_bounded_config(config_001, reference=reference, ratio=0.01)
    validate_memory_bounded_config(config_002, reference=reference, ratio=0.02)
    manifest = load_dataset_manifest(manifest_path)
    benchmark = load_public_benchmark(args.baseline_public_benchmark)
    if benchmark.dataset_manifest_sha256 != manifest.identity:
        raise ValueError("baseline public benchmark dataset identity mismatch")
    baselines = select_wallplugs_baselines(benchmark, baseline_config=baseline_config)
    frontier = _load_frontier_report(args.frontier_report)
    if frontier.dataset_manifest_sha256 != manifest.identity:
        raise ValueError("frontier dataset identity mismatch")
    specs = build_candidate_specs(
        config_001,
        config_002,
        dataset_manifest_sha256=manifest.identity,
    )
    dry_run = build_dry_run_payload(
        specs=specs,
        source_sha=revision,
        dataset_manifest_sha256=manifest.identity,
        reference_config_sha256=reference.identity,
        config_001_sha256=config_001.identity,
        config_002_sha256=config_002.identity,
        baseline_benchmark_sha256=benchmark.identity,
        frontier_report_sha256=frontier.identity,
    )
    if args.dry_run:
        print(json.dumps(dry_run, sort_keys=True))
        return None
    if output.exists():
        return _load_existing_report(output)

    preflight_limits = ResourceLimits(timeout_seconds=2_700)
    assert_resource_preflight(
        probe_resource_snapshot(),
        free_disk_bytes=shutil.disk_usage(runs_root.parent).free,
        limits=preflight_limits,
    )
    lock_path = (
        args.gpu_lock.expanduser().resolve()
        if args.gpu_lock is not None
        else runs_root.parent / ".mvtec-ad2-gpu.lock"
    )
    repository_identity = hashlib.sha256(str(repository).encode()).hexdigest()
    store = RunStore(runs_root)
    frontier_reference = cast(StudyComparison, frontier.comparison).candidate

    def run_candidate(spec: RunSpec) -> CandidateOutcome:
        ratio = _spec_ratio(spec)
        timeout = 2_700.0 if ratio == 0.01 else 3_600.0
        supervisor = Supervisor(
            store,
            runner=SubprocessExecutor(
                _attempt_command_factory(
                    data_root=data_root,
                    dataset_manifest=manifest_path,
                    device=args.device,
                    imagenette_root=None,
                ),
                resource_guard=ResourceGuard(limits=ResourceLimits(timeout_seconds=timeout)),
            ),
            gpu_lease=GpuLease(lock_path, repository_identity=repository_identity),
            code_revision=revision,
            environment_lock_sha256=sha256_file(repository / "uv.lock"),
            model_revision=lambda item: (
                f"anomalib:{item.config.get('anomalib_version')}/"
                f"{item.config.get('model_name')}/{item.config.get('backbone')}"
            ),
        )
        summary = supervisor.run((spec,))
        if spec.identity not in (*summary.completed, *summary.skipped):
            reason = summary.stop_reason or "candidate did not complete"
            resource_prefixes = (
                "system available memory",
                "GPU memory",
                "GPU temperature",
                "wall-clock limit",
            )
            if not reason.startswith(resource_prefixes):
                raise RuntimeError(f"candidate failed with preserved evidence: {spec.identity}")
            return CandidateOutcome(
                ratio=ratio,
                seed=cast(StudySeed, spec.seed),
                comparison=None,
                frontier_reference=None,
                resource_ok=False,
                resource_reason_sha256=hashlib.sha256(reason.encode()).hexdigest(),
            )

        record = store.load_record(store.run_dir(spec))
        if record.started_at is None or record.finished_at is None:
            raise ValueError("candidate run lacks timestamps")
        duration = record.finished_at - record.started_at
        if duration <= 0 or not math.isfinite(duration):
            raise ValueError("candidate run duration is invalid")
        with GpuLease(lock_path, repository_identity=repository_identity).acquire(
            "memory-bounded-patchcore-public"
        ):
            candidate = _evaluate_run(
                store=store,
                spec=spec,
                stage="screening" if spec.seed == 42 else "replication",
                data_root=data_root,
                dataset_manifest=manifest_path,
                evaluation_root=runs_root / "public-evaluation",
                device=args.device,
                imagenette_root=None,
            )
        if candidate.code_revision != revision:
            raise ValueError("candidate source revision mismatch")
        baseline = baselines[spec.seed]
        comparison = build_comparison(
            category=CATEGORY,
            baseline_run_identity=baseline.run_identity,
            candidate_run_identity=candidate.run_identity,
            baseline=StudyMetrics.from_public_metrics(baseline.metrics),
            candidate=StudyMetrics.from_public_metrics(candidate.metrics),
            candidate_duration_seconds=duration,
        )
        return CandidateOutcome(
            ratio=ratio,
            seed=cast(StudySeed, spec.seed),
            comparison=comparison,
            frontier_reference=frontier_reference if spec.seed == 42 else None,
        )

    probes: list[CandidateOutcome] = [run_candidate(specs[0])]
    next_specs = select_next_specs(specs, probes=tuple(probes))
    if next_specs == specs[1:2]:
        probes.append(run_candidate(specs[1]))
        next_specs = select_next_specs(specs, probes=tuple(probes))
    selected = select_ratio(tuple(probes))
    replications: list[CandidateOutcome] = []
    if selected is not None:
        for spec in next_specs:
            outcome = run_candidate(spec)
            replications.append(outcome)
            if not outcome.resource_ok:
                break

    if selected is None:
        verdict: StudyVerdict = (
            "RESOURCE_LIMIT_EXCEEDED"
            if any(not item.resource_ok for item in probes)
            else "NO_QUALITY_PRESERVATION"
        )
    elif any(not item.resource_ok for item in replications):
        verdict = "RESOURCE_LIMIT_EXCEEDED"
    else:
        if len(replications) != 2:
            raise ValueError("selected ratio did not produce two replication outcomes")
        selected_probe = next(item for item in probes if item.ratio == selected)
        verdict = classify_memory_bounded_study((selected_probe, replications[0], replications[1]))
    report = MemoryBoundedStudyReport(
        source_sha=revision,
        dataset_manifest_sha256=manifest.identity,
        baseline_benchmark_sha256=benchmark.identity,
        baseline_config_sha256=baseline_config.identity,
        reference_config_sha256=reference.identity,
        config_001_sha256=config_001.identity,
        config_002_sha256=config_002.identity,
        frontier_report_sha256=frontier.identity,
        probes=tuple(probes),
        selected_ratio=selected,
        replications=tuple(replications),
        verdict=verdict,
    )
    write_memory_bounded_report(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    report = execute_memory_bounded_study(build_parser().parse_args(argv))
    if report is not None:
        print(json.dumps({"report_sha256": report.identity, "status": report.verdict}))
    return 0


__all__ = [
    "CandidateOutcome",
    "MemoryBoundedStudyReport",
    "StudyVerdict",
    "build_candidate_specs",
    "build_dry_run_payload",
    "classify_memory_bounded_study",
    "passes_seed42_gate",
    "select_next_specs",
    "select_ratio",
    "validate_memory_bounded_config",
    "write_memory_bounded_report",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
