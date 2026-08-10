from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from experiments.evaluate_public import load_public_benchmark
from experiments.high_resolution_patchcore import StudyFailure, StudyMetrics, build_comparison
from experiments.models.base import ModelConfig, load_model_config
from experiments.patchcore_resolution_frontier import (
    FrontierReport,
    build_frontier_spec,
    classify_frontier,
    select_wallplugs_baseline,
    validate_frontier_config,
    write_frontier_report,
)


def _configs() -> tuple[ModelConfig, ModelConfig]:
    return (
        load_model_config(Path("experiments/configs/models/patchcore.yaml")),
        load_model_config(Path("experiments/configs/research/patchcore-640.yaml")),
    )


def _metrics(au_pro: float, *, vram: float = 4_000.0) -> StudyMetrics:
    return StudyMetrics(
        au_pro=au_pro,
        image_auroc=0.7,
        pixel_auroc=0.8,
        gpu_p95_latency_ms=100.0,
        peak_vram_mib=vram,
        artifact_size_bytes=1_000,
        per_image_failure_rate=0.0,
    )


def _comparison(delta: float = 0.03, *, vram: float = 4_000.0):
    return build_comparison(
        category="wallplugs",
        baseline_run_identity="a" * 64,
        candidate_run_identity="b" * 64,
        baseline=_metrics(0.5),
        candidate=_metrics(0.5 + delta, vram=vram),
        candidate_duration_seconds=600.0,
    )


def test_frontier_spec_is_exactly_wallplugs_640_seed_42() -> None:
    baseline, candidate = _configs()

    validate_frontier_config(candidate, baseline=baseline)
    spec = build_frontier_spec(candidate, dataset_manifest_sha256="c" * 64)

    assert spec.category == "wallplugs"
    assert spec.seed == 42
    assert spec.config["input_size"] == [640, 640]


def test_frontier_rejects_any_change_beyond_geometry() -> None:
    baseline, candidate = _configs()
    payload = candidate.model_dump(mode="json", exclude_computed_fields=True)
    options = deepcopy(payload["family_options"])
    assert isinstance(options, dict)
    options["coreset_sampling_ratio"] = 0.05
    payload["family_options"] = options

    with pytest.raises(ValueError, match=r"only input_size and preprocessing\.resize"):
        validate_frontier_config(ModelConfig.model_validate(payload), baseline=baseline)


def test_frontier_selects_the_frozen_wallplugs_baseline() -> None:
    baseline, _ = _configs()
    benchmark = load_public_benchmark(Path("reports/public_benchmark.json"))

    selected = select_wallplugs_baseline(benchmark, baseline_config=baseline)

    assert selected.run_identity == (
        "6ffd7c77dc95549ae174f324c19684a44a90808029672390c07cc72df9874972"
    )


@pytest.mark.parametrize(
    ("comparison", "failed", "expected"),
    [
        (_comparison(0.03), False, "PROMISING"),
        (_comparison(0.01), False, "NO_CLEAR_GAIN"),
        (_comparison(-0.03), False, "REGRESSION"),
        (_comparison(0.03, vram=12_289.0), False, "RESOURCE_LIMIT_EXCEEDED"),
        (None, True, "RESOURCE_LIMIT_EXCEEDED"),
    ],
)
def test_frontier_classification_is_frozen(comparison, failed: bool, expected: str) -> None:
    assert classify_frontier(comparison, failed=failed) == expected


def test_frontier_report_is_identity_bound_and_public_only(tmp_path: Path) -> None:
    comparison = _comparison()
    report = FrontierReport(
        source_sha="d" * 40,
        dataset_manifest_sha256="e" * 64,
        baseline_benchmark_sha256="f" * 64,
        baseline_config_sha256="1" * 64,
        candidate_config_sha256="2" * 64,
        candidate_training_peak_vram_mib=22_000.0,
        comparison=comparison,
        verdict="PROMISING",
    )

    destination = write_frontier_report(tmp_path / "frontier.json", report)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["canonical_sha256"] == report.identity
    assert payload["scope"] == "test_public-only"
    assert payload["submitted"] is False
    assert "prediction" not in destination.read_text(encoding="utf-8")


def test_frontier_failure_report_contains_only_sanitized_evidence(tmp_path: Path) -> None:
    failure = StudyFailure(
        category="wallplugs",
        candidate_run_identity="a" * 64,
        code_revision="b" * 40,
        candidate_duration_seconds=30.0,
        attempt=1,
        exit_code=1,
        error_kind="oom",
        error_sha256="c" * 64,
    )
    report = FrontierReport(
        source_sha="d" * 40,
        dataset_manifest_sha256="e" * 64,
        baseline_benchmark_sha256="f" * 64,
        baseline_config_sha256="1" * 64,
        candidate_config_sha256="2" * 64,
        failure=failure,
        verdict="RESOURCE_LIMIT_EXCEEDED",
    )

    destination = write_frontier_report(tmp_path / "failure.json", report)

    assert "OutOfMemoryError" not in destination.read_text(encoding="utf-8")


def test_committed_frontier_result_is_public_only_and_keeps_champion() -> None:
    destination = Path("reports/patchcore_resolution_frontier.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    claimed_identity = payload.pop("canonical_sha256")
    report = FrontierReport.model_validate(payload)
    champions = json.loads(Path("reports/champions.json").read_text(encoding="utf-8"))

    assert report.identity == claimed_identity
    assert report.scope == "test_public-only"
    assert report.submitted is False
    assert report.verdict == "PROMISING"
    assert report.comparison is not None
    assert report.comparison.au_pro_delta == pytest.approx(0.06952117214205145)
    assert report.comparison.image_auroc_delta == pytest.approx(-0.04055555555555568)
    assert report.candidate_training_peak_vram_mib == pytest.approx(22219.03564453125)
    assert champions["champions"]["wallplugs"] == "patchcore"
