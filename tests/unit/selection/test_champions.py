from __future__ import annotations

from pathlib import Path

import pytest

from experiments.evaluate_public import (
    BenchmarkRunEvidence,
    PublicBenchmark,
    write_public_benchmark,
)
from experiments.reports.render_benchmark import render_markdown, validate_benchmark_schema
from experiments.select_champions import CandidateEvidence, freeze_champions, select_champion
from experiments.select_contenders import select_contenders


def candidate(
    family: str,
    *,
    au_pro: float = 0.5,
    au_pro_ci: tuple[float, float] = (-0.01, 0.01),
    image_auroc: float = 0.8,
    image_ci: tuple[float, float] = (-0.01, 0.01),
    p95: float = 10.0,
    vram: float = 4_000.0,
    size: int = 1_000,
) -> CandidateEvidence:
    return CandidateEvidence.model_validate(
        {
            "family": family,
            "au_pro": au_pro,
            "au_pro_delta_ci_vs_other": au_pro_ci,
            "image_auroc": image_auroc,
            "image_auroc_delta_ci_vs_other": image_ci,
            "gpu_p95_latency_ms": p95,
            "peak_vram_mib": vram,
            "artifact_size_bytes": size,
            "run_identities": ["a" * 64, "b" * 64, "c" * 64],
        }
    )


def test_significant_au_pro_difference_selects_higher_localization_quality() -> None:
    decision = select_champion(
        [
            candidate("patchcore", au_pro=0.60, au_pro_ci=(0.02, 0.08)),
            candidate("dinomaly", au_pro=0.55, au_pro_ci=(-0.08, -0.02)),
        ]
    )

    assert decision.winner == "patchcore"
    assert decision.reason == "significant_higher_au_pro"


def test_unresolved_au_pro_uses_significant_image_auroc() -> None:
    decision = select_champion(
        [
            candidate(
                "patchcore",
                au_pro=0.60,
                image_auroc=0.80,
                image_ci=(-0.08, -0.02),
            ),
            candidate(
                "dinomaly",
                au_pro=0.59,
                image_auroc=0.86,
                image_ci=(0.02, 0.08),
            ),
        ]
    )

    assert decision.winner == "dinomaly"
    assert decision.reason == "localization_unresolved_significant_higher_image_auroc"


def test_unresolved_quality_prefers_lower_latency() -> None:
    decision = select_champion(
        [
            candidate("patchcore", au_pro=0.50, p95=8.0),
            candidate("dinomaly", au_pro=0.51, p95=12.0),
        ]
    )

    assert decision.winner == "patchcore"
    assert decision.reason == "quality_unresolved_lower_gpu_p95"


def test_latency_within_five_percent_prefers_lower_vram() -> None:
    decision = select_champion(
        [
            candidate("patchcore", p95=10.0, vram=4_000.0),
            candidate("dinomaly", p95=10.4, vram=6_000.0),
        ]
    )

    assert decision.winner == "patchcore"
    assert decision.reason == "latency_within_5_percent_lower_peak_vram"


def test_vram_within_five_percent_prefers_smaller_artifact() -> None:
    decision = select_champion(
        [
            candidate("patchcore", p95=10.0, vram=4_000.0, size=2_000),
            candidate("dinomaly", p95=10.4, vram=4_100.0, size=1_000),
        ]
    )

    assert decision.winner == "dinomaly"
    assert decision.reason == "latency_and_vram_within_5_percent_smaller_artifact"


def test_selection_requires_exactly_two_distinct_candidates() -> None:
    with pytest.raises(ValueError, match="exactly two"):
        select_champion([candidate("patchcore")])
    with pytest.raises(ValueError, match="distinct"):
        select_champion([candidate("patchcore"), candidate("patchcore")])


def test_screening_selects_exactly_two_highest_au_pro_models_per_category(
    tmp_path: Path,
) -> None:
    runs = []
    for category in (
        "can",
        "fabric",
        "fruit_jelly",
        "rice",
        "sheet_metal",
        "vial",
        "wallplugs",
        "walnuts",
    ):
        for family, au_pro in (
            ("patchcore", 0.8),
            ("efficient_ad", 0.6),
            ("dinomaly", 0.7),
        ):
            runs.append(benchmark_run(category, family, au_pro=au_pro))
    benchmark = PublicBenchmark(
        experiment_version="v1",
        dataset_manifest_sha256="d" * 64,
        public_gate_identity="e" * 64,
        runs=tuple(runs),
    )

    artifact = select_contenders(benchmark)

    assert len(benchmark.screening_macro) == 3
    patchcore_macro = next(item for item in benchmark.screening_macro if item.family == "patchcore")
    assert patchcore_macro.au_pro.mean == pytest.approx(0.8)
    assert artifact.contenders["can"] == ("patchcore", "dinomaly")
    assert len(artifact.decisions) == 8
    assert artifact.decisions[0].rationale == "top_two_seed_42_public_au_pro"
    benchmark_path = write_public_benchmark(tmp_path / "benchmark.json", benchmark)
    validate_benchmark_schema(
        benchmark_path,
        Path("reports/schemas/benchmark.schema.json"),
    )


def benchmark_run(
    category: str,
    family: str,
    *,
    au_pro: float,
    seed: int = 42,
    p95: float = 11.0,
) -> BenchmarkRunEvidence:
    return BenchmarkRunEvidence.model_validate(
        {
            "stage": "screening",
            "run_identity": (category + family + str(seed)).encode().hex().ljust(64, "0")[:64],
            "family": family,
            "category": category,
            "seed": seed,
            "dataset_manifest_sha256": "d" * 64,
            "code_revision": "abc123",
            "config_sha256": "1" * 64,
            "environment_lock_sha256": "2" * 64,
            "model_revision": "model-v1",
            "checkpoint_sha256": "3" * 64,
            "threshold_artifact_sha256": "4" * 64,
            "prediction_artifact_sha256": "5" * 64,
            "prediction_locator": f"public-evaluation/{category}-{family}/test_public.json",
            "run_record_sha256": "6" * 64,
            "metrics": {
                "image": {
                    "auroc": 0.9,
                    "average_precision": 0.9,
                    "normal_count": 1,
                    "anomaly_count": 1,
                },
                "pixel": {
                    "auroc": 0.9,
                    "average_precision": 0.9,
                    "au_pro": au_pro,
                    "normal_pixel_count": 3,
                    "anomaly_pixel_count": 1,
                    "region_count": 1,
                },
                "operating": {
                    "threshold": 0.5,
                    "public_normal_false_review_rate": 0.0,
                    "public_anomaly_recall": 1.0,
                    "public_review_precision": 1.0,
                    "public_review_f1": 1.0,
                    "expected_reviews_per_1000_normal": 0.0,
                },
                "gpu_latency": {
                    "samples": 2,
                    "p50_ms": 10.0,
                    "p95_ms": p95,
                    "throughput_images_per_second": 100.0,
                    "setup_latency_ms": 50.0,
                },
                "peak_vram_mib": 1000.0,
                "artifact_size_bytes": 100,
            },
        }
    )


def test_replication_freezes_one_champion_from_three_seeds_per_contender() -> None:
    runs = []
    for category in (
        "can",
        "fabric",
        "fruit_jelly",
        "rice",
        "sheet_metal",
        "vial",
        "wallplugs",
        "walnuts",
    ):
        for family, au_pro, p95 in (
            ("patchcore", 0.8, 8.0),
            ("efficient_ad", 0.6, 10.0),
            ("dinomaly", 0.8, 12.0),
        ):
            runs.append(benchmark_run(category, family, au_pro=au_pro, p95=p95))
        for seed in (17, 2026):
            runs.append(
                benchmark_run(
                    category,
                    "patchcore",
                    au_pro=0.8,
                    seed=seed,
                    p95=8.0,
                ).model_copy(update={"stage": "replication"})
            )
            runs.append(
                benchmark_run(
                    category,
                    "dinomaly",
                    au_pro=0.8,
                    seed=seed,
                    p95=12.0,
                ).model_copy(update={"stage": "replication"})
            )
    benchmark = PublicBenchmark(
        experiment_version="v1",
        dataset_manifest_sha256="d" * 64,
        public_gate_identity="e" * 64,
        runs=tuple(runs),
    )
    screening_benchmark = PublicBenchmark(
        experiment_version="v1",
        dataset_manifest_sha256="d" * 64,
        public_gate_identity="e" * 64,
        runs=tuple(run for run in runs if run.stage == "screening"),
    )
    contenders = select_contenders(screening_benchmark)

    champions = freeze_champions(benchmark, contenders, resamples=257)

    assert champions.champions["can"] == "patchcore"
    assert len(champions.decisions) == 8
    assert champions.decisions[0].decision.reason == "quality_unresolved_lower_gpu_p95"

    markdown = render_markdown(benchmark, champions)
    assert benchmark.identity in markdown
    assert champions.identity in markdown
    assert "| can | patchcore | 0.800000 | 0.900000 | 8.000 |" in markdown
    winner = next(
        item
        for item in champions.decisions[0].candidates
        if item.family == champions.decisions[0].decision.winner
    )
    assert winner.run_identities[0] in markdown
    assert all(line == line.rstrip() for line in markdown.splitlines())
