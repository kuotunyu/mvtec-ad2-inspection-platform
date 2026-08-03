from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, Self, cast

import numpy as np
from pydantic import Field, model_validator

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.evaluate_public import PublicBenchmark, load_public_benchmark
from experiments.metrics.bootstrap import paired_bootstrap_delta
from experiments.select_contenders import ContendersArtifact
from inspection_platform.contracts import ModelFamily, canonical_hash
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256

SelectionReason = Literal[
    "significant_higher_au_pro",
    "localization_unresolved_significant_higher_image_auroc",
    "quality_unresolved_lower_gpu_p95",
    "latency_within_5_percent_lower_peak_vram",
    "latency_and_vram_within_5_percent_smaller_artifact",
    "exact_evidence_tie_stable_family_order",
]


class CandidateEvidence(ContractModel):
    family: ModelFamily
    au_pro: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    au_pro_delta_ci_vs_other: tuple[float, float]
    image_auroc: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    image_auroc_delta_ci_vs_other: tuple[float, float]
    gpu_p95_latency_ms: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    peak_vram_mib: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    artifact_size_bytes: Annotated[int, Field(gt=0)]
    run_identities: Annotated[tuple[Sha256, Sha256, Sha256], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def require_ordered_intervals(self) -> Self:
        for lower, upper in (
            self.au_pro_delta_ci_vs_other,
            self.image_auroc_delta_ci_vs_other,
        ):
            if lower > upper:
                raise ValueError("confidence interval lower bound must not exceed upper bound")
        return self


class SelectionDecision(ContractModel):
    winner: ModelFamily
    loser: ModelFamily
    reason: SelectionReason


class CategoryChampionDecision(ContractModel):
    category: MVTecAD2Category
    candidates: Annotated[tuple[CandidateEvidence, ...], Field(min_length=2, max_length=2)]
    decision: SelectionDecision
    bootstrap_seed: int
    bootstrap_resamples: Annotated[int, Field(gt=0)]


class ChampionsArtifact(ContractModel):
    experiment_version: str
    dataset_manifest_sha256: Sha256
    public_benchmark_sha256: Sha256
    public_gate_identity: Sha256
    contenders_sha256: Sha256
    champions: dict[MVTecAD2Category, ModelFamily]
    decisions: Annotated[tuple[CategoryChampionDecision, ...], Field(min_length=8, max_length=8)]

    @model_validator(mode="after")
    def require_complete_categories(self) -> Self:
        if set(self.champions) != set(REQUIRED_CATEGORIES):
            raise ValueError("champions must contain all eight categories")
        if {decision.category for decision in self.decisions} != set(REQUIRED_CATEGORIES):
            raise ValueError("champion decisions must contain all eight categories")
        if any(
            self.champions[decision.category] != decision.decision.winner
            for decision in self.decisions
        ):
            raise ValueError("champion map differs from category decisions")
        return self

    @property
    def identity(self) -> str:
        return canonical_hash(self)


def _within_five_percent(left: float, right: float) -> bool:
    return abs(left - right) / min(left, right) < 0.05


def _significantly_better(candidate: CandidateEvidence, *, metric: str) -> bool:
    interval = (
        candidate.au_pro_delta_ci_vs_other
        if metric == "au_pro"
        else candidate.image_auroc_delta_ci_vs_other
    )
    return interval[0] > 0.0


def _decision(
    winner: CandidateEvidence,
    loser: CandidateEvidence,
    reason: SelectionReason,
) -> SelectionDecision:
    return SelectionDecision(winner=winner.family, loser=loser.family, reason=reason)


def select_champion(candidates: Sequence[CandidateEvidence]) -> SelectionDecision:
    """Apply the approved localization, discrimination, and engineering tie-breaks."""

    if len(candidates) != 2:
        raise ValueError("champion selection requires exactly two candidates")
    left, right = candidates
    if left.family == right.family:
        raise ValueError("champion selection candidates must be distinct")

    localization_leader = max(candidates, key=lambda item: (item.au_pro, item.family))
    localization_other = right if localization_leader is left else left
    if _significantly_better(localization_leader, metric="au_pro"):
        return _decision(
            localization_leader,
            localization_other,
            "significant_higher_au_pro",
        )

    image_leader = max(candidates, key=lambda item: (item.image_auroc, item.family))
    image_other = right if image_leader is left else left
    if _significantly_better(image_leader, metric="image_auroc"):
        return _decision(
            image_leader,
            image_other,
            "localization_unresolved_significant_higher_image_auroc",
        )

    latency_leader = min(candidates, key=lambda item: (item.gpu_p95_latency_ms, item.family))
    latency_other = right if latency_leader is left else left
    if not _within_five_percent(
        latency_leader.gpu_p95_latency_ms, latency_other.gpu_p95_latency_ms
    ):
        return _decision(
            latency_leader,
            latency_other,
            "quality_unresolved_lower_gpu_p95",
        )

    vram_leader = min(candidates, key=lambda item: (item.peak_vram_mib, item.family))
    vram_other = right if vram_leader is left else left
    if not _within_five_percent(vram_leader.peak_vram_mib, vram_other.peak_vram_mib):
        return _decision(
            vram_leader,
            vram_other,
            "latency_within_5_percent_lower_peak_vram",
        )

    size_leader = min(candidates, key=lambda item: (item.artifact_size_bytes, item.family))
    size_other = right if size_leader is left else left
    if size_leader.artifact_size_bytes != size_other.artifact_size_bytes:
        return _decision(
            size_leader,
            size_other,
            "latency_and_vram_within_5_percent_smaller_artifact",
        )

    stable = min(candidates, key=lambda item: item.family)
    other = right if stable is left else left
    return _decision(stable, other, "exact_evidence_tie_stable_family_order")


def _candidate_evidence(
    family: ModelFamily,
    other: ModelFamily,
    category_runs: Sequence[object],
    *,
    bootstrap_seed: int,
    resamples: int,
) -> CandidateEvidence:
    from experiments.evaluate_public import BenchmarkRunEvidence

    typed_runs = cast(Sequence[BenchmarkRunEvidence], category_runs)
    own = sorted((run for run in typed_runs if run.family == family), key=lambda run: run.seed)
    competing = sorted((run for run in typed_runs if run.family == other), key=lambda run: run.seed)
    if [run.seed for run in own] != [17, 42, 2026] or [run.seed for run in competing] != [
        17,
        42,
        2026,
    ]:
        raise ValueError("champion selection requires seeds 17/42/2026 for both contenders")
    own_au_pro = np.asarray(
        [cast(float, run.metrics.pixel.au_pro) for run in own], dtype=np.float64
    )
    other_au_pro = np.asarray(
        [cast(float, run.metrics.pixel.au_pro) for run in competing], dtype=np.float64
    )
    own_image = np.asarray([cast(float, run.metrics.image.auroc) for run in own], dtype=np.float64)
    other_image = np.asarray(
        [cast(float, run.metrics.image.auroc) for run in competing], dtype=np.float64
    )
    if not all(
        np.isfinite(array).all() for array in (own_au_pro, other_au_pro, own_image, other_image)
    ):
        raise ValueError("champion selection metrics must be defined and finite")
    au_pro_ci = paired_bootstrap_delta(
        own_au_pro,
        other_au_pro,
        seed=bootstrap_seed,
        resamples=resamples,
    )
    image_ci = paired_bootstrap_delta(
        own_image,
        other_image,
        seed=bootstrap_seed,
        resamples=resamples,
    )
    return CandidateEvidence(
        family=family,
        au_pro=float(np.mean(own_au_pro)),
        au_pro_delta_ci_vs_other=(au_pro_ci.lower, au_pro_ci.upper),
        image_auroc=float(np.mean(own_image)),
        image_auroc_delta_ci_vs_other=(image_ci.lower, image_ci.upper),
        gpu_p95_latency_ms=max(run.metrics.gpu_latency.p95_ms for run in own),
        peak_vram_mib=max(run.metrics.peak_vram_mib for run in own),
        artifact_size_bytes=max(run.metrics.artifact_size_bytes for run in own),
        run_identities=cast(tuple[str, str, str], tuple(run.run_identity for run in own)),
    )


def freeze_champions(
    benchmark: PublicBenchmark,
    contenders: ContendersArtifact,
    *,
    bootstrap_seed: int = 42,
    resamples: int = 10_000,
) -> ChampionsArtifact:
    if (
        contenders.experiment_version != benchmark.experiment_version
        or contenders.dataset_manifest_sha256 != benchmark.dataset_manifest_sha256
        or contenders.public_gate_identity != benchmark.public_gate_identity
    ):
        raise ValueError("contenders are incompatible with the public benchmark")
    screening_snapshot = PublicBenchmark(
        experiment_version=benchmark.experiment_version,
        dataset_manifest_sha256=benchmark.dataset_manifest_sha256,
        public_gate_identity=benchmark.public_gate_identity,
        runs=tuple(run for run in benchmark.runs if run.stage == "screening"),
    )
    if contenders.public_benchmark_sha256 != screening_snapshot.identity:
        raise ValueError("contenders are not traceable to the frozen screening benchmark")
    decisions: list[CategoryChampionDecision] = []
    champions: dict[MVTecAD2Category, ModelFamily] = {}
    for raw_category in REQUIRED_CATEGORIES:
        category = cast(MVTecAD2Category, raw_category)
        families = contenders.contenders[category]
        category_runs = [
            run for run in benchmark.runs if run.category == category and run.family in families
        ]
        if len(category_runs) != 6:
            raise ValueError(f"category {category} lacks six contender replication runs")
        left = _candidate_evidence(
            families[0],
            families[1],
            category_runs,
            bootstrap_seed=bootstrap_seed,
            resamples=resamples,
        )
        right = _candidate_evidence(
            families[1],
            families[0],
            category_runs,
            bootstrap_seed=bootstrap_seed,
            resamples=resamples,
        )
        decision = select_champion((left, right))
        champions[category] = decision.winner
        decisions.append(
            CategoryChampionDecision(
                category=category,
                candidates=(left, right),
                decision=decision,
                bootstrap_seed=bootstrap_seed,
                bootstrap_resamples=resamples,
            )
        )
    return ChampionsArtifact(
        experiment_version=benchmark.experiment_version,
        dataset_manifest_sha256=benchmark.dataset_manifest_sha256,
        public_benchmark_sha256=benchmark.identity,
        public_gate_identity=benchmark.public_gate_identity,
        contenders_sha256=contenders.identity,
        champions=champions,
        decisions=tuple(decisions),
    )


def load_contenders(path: Path) -> ContendersArtifact:
    payload = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("contenders root must be an object")
    canonical = payload.pop("canonical_sha256", None)
    artifact = ContendersArtifact.model_validate(payload)
    if canonical != artifact.identity:
        raise ValueError("contenders canonical identity mismatch")
    return artifact


def write_champions(path: Path, artifact: ChampionsArtifact) -> Path:
    resolved = path.expanduser().resolve()
    payload = artifact.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = artifact.identity
    if resolved.exists():
        if json.loads(resolved.read_text(encoding="utf-8")) != payload:
            raise ValueError("refusing to overwrite frozen champions")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze one champion per category")
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--contenders", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap-seed", type=int, default=42)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runs_value = os.environ.get("MVTECAD2_RUNS_ROOT")
    evidence_root = Path(runs_value).expanduser().resolve() / "evidence" if runs_value else None
    benchmark_path = (
        args.benchmark.expanduser().resolve(strict=True)
        if args.benchmark is not None
        else evidence_root / "public_benchmark.json"
        if evidence_root is not None
        else Path("reports/public_benchmark.json").resolve(strict=True)
    )
    contenders_path = (
        args.contenders.expanduser().resolve(strict=True)
        if args.contenders is not None
        else evidence_root / "contenders.json"
        if evidence_root is not None
        else Path("reports/contenders.json").resolve(strict=True)
    )
    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else evidence_root / "champions.json"
        if evidence_root is not None
        else Path("reports/champions.json").resolve()
    )
    artifact = freeze_champions(
        load_public_benchmark(benchmark_path),
        load_contenders(contenders_path),
        bootstrap_seed=args.bootstrap_seed,
        resamples=args.bootstrap_resamples,
    )
    write_champions(output_path, artifact)
    print(
        json.dumps(
            {"champions_sha256": artifact.identity, "output": str(output_path)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
