from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import Field, computed_field, model_validator

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.evaluate_public import PublicBenchmark, load_public_benchmark
from inspection_platform.contracts import ModelFamily, canonical_hash
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256


class ContenderRanking(ContractModel):
    family: ModelFamily
    public_au_pro: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    public_image_auroc: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    run_identity: Sha256


class ContenderDecision(ContractModel):
    category: MVTecAD2Category
    contenders: tuple[ModelFamily, ModelFamily]
    excluded: ModelFamily
    ranking: Annotated[tuple[ContenderRanking, ...], Field(min_length=3, max_length=3)]
    rationale: Literal["top_two_seed_42_public_au_pro"] = "top_two_seed_42_public_au_pro"


class ContendersArtifact(ContractModel):
    experiment_version: str
    dataset_manifest_sha256: Sha256
    public_benchmark_sha256: Sha256
    public_gate_identity: Sha256
    contenders: dict[MVTecAD2Category, tuple[ModelFamily, ModelFamily]]
    decisions: Annotated[tuple[ContenderDecision, ...], Field(min_length=8, max_length=8)]

    @model_validator(mode="after")
    def require_complete_categories(self) -> ContendersArtifact:
        if set(self.contenders) != set(REQUIRED_CATEGORIES):
            raise ValueError("contender artifact must contain all eight categories")
        if {decision.category for decision in self.decisions} != set(REQUIRED_CATEGORIES):
            raise ValueError("contender decisions must contain all eight categories")
        if any(len(set(families)) != 2 for families in self.contenders.values()):
            raise ValueError("every category must contain two distinct contenders")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)


def select_contenders(benchmark: PublicBenchmark) -> ContendersArtifact:
    screening = [run for run in benchmark.runs if run.stage == "screening"]
    if len(screening) != 24 or len(benchmark.runs) != 24:
        raise ValueError("contender selection requires exactly 24 screening runs")
    decisions: list[ContenderDecision] = []
    contenders: dict[MVTecAD2Category, tuple[ModelFamily, ModelFamily]] = {}
    for raw_category in REQUIRED_CATEGORIES:
        category = cast(MVTecAD2Category, raw_category)
        category_runs = [run for run in screening if run.category == category]
        if len(category_runs) != 3 or any(run.seed != 42 for run in category_runs):
            raise ValueError(f"category {category} lacks its three seed-42 screening runs")
        if {run.family for run in category_runs} != {
            "patchcore",
            "efficient_ad",
            "dinomaly",
        }:
            raise ValueError(f"category {category} has an invalid screening family set")
        if any(
            run.metrics.pixel.au_pro is None or run.metrics.image.auroc is None
            for run in category_runs
        ):
            raise ValueError(f"category {category} has undefined selection metrics")
        ordered = sorted(
            category_runs,
            key=lambda run: (
                -cast(float, run.metrics.pixel.au_pro),
                -cast(float, run.metrics.image.auroc),
                run.family,
            ),
        )
        selected = (ordered[0].family, ordered[1].family)
        contenders[category] = selected
        decisions.append(
            ContenderDecision(
                category=category,
                contenders=selected,
                excluded=ordered[2].family,
                ranking=tuple(
                    ContenderRanking(
                        family=run.family,
                        public_au_pro=cast(float, run.metrics.pixel.au_pro),
                        public_image_auroc=cast(float, run.metrics.image.auroc),
                        run_identity=run.run_identity,
                    )
                    for run in ordered
                ),
            )
        )
    return ContendersArtifact(
        experiment_version=benchmark.experiment_version,
        dataset_manifest_sha256=benchmark.dataset_manifest_sha256,
        public_benchmark_sha256=benchmark.identity,
        public_gate_identity=benchmark.public_gate_identity,
        contenders=contenders,
        decisions=tuple(decisions),
    )


def write_contenders(path: Path, artifact: ContendersArtifact) -> Path:
    resolved = path.expanduser().resolve()
    payload = artifact.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = artifact.identity
    if resolved.exists():
        if json.loads(resolved.read_text(encoding="utf-8")) != payload:
            raise ValueError("refusing to overwrite frozen contenders")
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
    parser = argparse.ArgumentParser(description="Freeze two public contenders per category")
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--output", type=Path)
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
    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else evidence_root / "contenders.json"
        if evidence_root is not None
        else Path("reports/contenders.json").resolve()
    )
    artifact = select_contenders(load_public_benchmark(benchmark_path))
    write_contenders(output_path, artifact)
    print(
        json.dumps(
            {"contenders_sha256": artifact.identity, "output": str(output_path)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
