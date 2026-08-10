from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from experiments.balanced_patchcore_study import (
    BalancedStudyReport,
    StageBProbeReport,
    build_candidate_specs,
    classify_stage_a,
    classify_stage_b,
    passes_stage_b_advance,
    select_followup_specs,
    select_wallplugs_baselines,
    validate_balanced_config,
    write_balanced_report,
    write_stage_b_probe_report,
)
from experiments.evaluate_public import load_public_benchmark
from experiments.high_resolution_patchcore import StudyMetrics, build_comparison
from experiments.models.base import ModelConfig, load_model_config


def _metrics(
    au_pro: float,
    *,
    image_auroc: float = 0.70,
    pixel_auroc: float = 0.80,
    latency: float = 100.0,
    failures: float = 0.0,
) -> StudyMetrics:
    return StudyMetrics(
        au_pro=au_pro,
        image_auroc=image_auroc,
        pixel_auroc=pixel_auroc,
        gpu_p95_latency_ms=latency,
        peak_vram_mib=2_000.0,
        artifact_size_bytes=1_000,
        per_image_failure_rate=failures,
    )


def _comparison(
    au_pro_delta: float,
    *,
    image_delta: float = 0.0,
    pixel_delta: float = 0.0,
    latency: float = 100.0,
    failures: float = 0.0,
):
    return build_comparison(
        category="wallplugs",
        baseline_run_identity="a" * 64,
        candidate_run_identity="b" * 64,
        baseline=_metrics(0.50),
        candidate=_metrics(
            0.50 + au_pro_delta,
            image_auroc=0.70 + image_delta,
            pixel_auroc=0.80 + pixel_delta,
            latency=latency,
            failures=failures,
        ),
        candidate_duration_seconds=600.0,
    )


def _configs() -> tuple[ModelConfig, ModelConfig, ModelConfig]:
    return (
        load_model_config(Path("experiments/configs/models/patchcore.yaml")),
        load_model_config(Path("experiments/configs/research/patchcore-640.yaml")),
        load_model_config(Path("experiments/configs/research/patchcore-576.yaml")),
    )


def test_candidate_configs_change_only_geometry() -> None:
    baseline, config_640, config_576 = _configs()

    validate_balanced_config(config_640, baseline=baseline, resolution=(640, 640))
    validate_balanced_config(config_576, baseline=baseline, resolution=(576, 576))


def test_candidate_config_rejects_non_geometry_change() -> None:
    baseline, _, config_576 = _configs()
    payload = config_576.model_dump(mode="json", exclude_computed_fields=True)
    options = deepcopy(payload["family_options"])
    assert isinstance(options, dict)
    options["coreset_sampling_ratio"] = 0.05
    payload["family_options"] = options

    with pytest.raises(ValueError, match=r"only input_size and preprocessing\.resize"):
        validate_balanced_config(
            ModelConfig.model_validate(payload), baseline=baseline, resolution=(576, 576)
        )


def test_fixed_specs_exclude_completed_640_seed_42() -> None:
    _, config_640, config_576 = _configs()

    specs = build_candidate_specs(config_640, config_576, dataset_manifest_sha256="c" * 64)

    assert [(spec.seed, spec.config["input_size"]) for spec in specs] == [
        (17, [640, 640]),
        (2026, [640, 640]),
        (42, [576, 576]),
        (17, [576, 576]),
        (2026, [576, 576]),
    ]
    assert all(spec.category == "wallplugs" for spec in specs)


@pytest.mark.parametrize(
    ("comparisons", "failed", "expected"),
    [
        (
            (_comparison(0.069), _comparison(0.03), _comparison(0.01)),
            False,
            "REPRODUCIBLE_LOCALIZATION_GAIN",
        ),
        ((_comparison(0.03), _comparison(0.025), _comparison(-0.03)), False, "MIXED"),
        ((_comparison(0.01), _comparison(0.0), _comparison(-0.01)), False, "NO_CLEAR_GAIN"),
        (
            (_comparison(0.03), _comparison(0.03), _comparison(0.03)),
            True,
            "RESOURCE_LIMIT_EXCEEDED",
        ),
        (
            (_comparison(0.03, latency=501.0), _comparison(0.03), _comparison(0.03)),
            False,
            "RESOURCE_LIMIT_EXCEEDED",
        ),
    ],
)
def test_stage_a_classification_is_frozen(comparisons, failed: bool, expected: str) -> None:
    assert classify_stage_a(comparisons, failed=failed) == expected


def test_stage_b_seed_42_advance_gate_is_balanced() -> None:
    assert passes_stage_b_advance(_comparison(0.03, image_delta=-0.005, pixel_delta=0.001))
    assert not passes_stage_b_advance(_comparison(0.03, image_delta=-0.011, pixel_delta=0.001))
    assert not passes_stage_b_advance(_comparison(0.03, image_delta=-0.005, pixel_delta=-0.006))


@pytest.mark.parametrize(
    ("comparisons", "failed", "expected"),
    [
        (
            (
                _comparison(0.03, image_delta=-0.005, pixel_delta=0.002),
                _comparison(0.025, image_delta=-0.01, pixel_delta=0.001),
                _comparison(0.02, image_delta=0.0, pixel_delta=0.0),
            ),
            False,
            "BALANCED_PROMISING",
        ),
        (
            (
                _comparison(0.03, image_delta=-0.04),
                _comparison(0.03),
                _comparison(0.03),
            ),
            False,
            "MIXED",
        ),
        ((_comparison(0.01), _comparison(0.0), _comparison(-0.01)), False, "NO_CLEAR_GAIN"),
        (
            (_comparison(0.03), _comparison(0.03), _comparison(0.03)),
            True,
            "RESOURCE_LIMIT_EXCEEDED",
        ),
    ],
)
def test_stage_b_classification_is_frozen(comparisons, failed: bool, expected: str) -> None:
    assert classify_stage_b(comparisons, failed=failed) == expected


def test_selects_one_matching_baseline_for_each_seed() -> None:
    baseline, _, _ = _configs()
    benchmark = load_public_benchmark(Path("reports/public_benchmark.json"))

    selected = select_wallplugs_baselines(benchmark, baseline_config=baseline)

    assert tuple(selected) == (42, 17, 2026)
    assert (
        selected[42].run_identity
        == "6ffd7c77dc95549ae174f324c19684a44a90808029672390c07cc72df9874972"
    )
    assert (
        selected[17].run_identity
        == "437a3d6f63e9ce551bc6710738cbaab22121f5b3bc592dace57dacfcec636d97"
    )
    assert (
        selected[2026].run_identity
        == "e2517d5a507bf2a0da8e99af47a485fd88c0d900d4d8773966750afad8d7009f"
    )


def test_report_is_identity_bound_public_only_and_idempotent(tmp_path: Path) -> None:
    stage_a = (_comparison(0.069), _comparison(0.03), _comparison(0.01))
    stage_b = (
        _comparison(0.03, image_delta=-0.005, pixel_delta=0.001),
        _comparison(0.025, image_delta=-0.005, pixel_delta=0.001),
        _comparison(0.02, image_delta=0.0, pixel_delta=0.0),
    )
    report = BalancedStudyReport(
        source_sha="d" * 40,
        dataset_manifest_sha256="e" * 64,
        baseline_benchmark_sha256="f" * 64,
        baseline_config_sha256="1" * 64,
        config_640_sha256="2" * 64,
        config_576_sha256="3" * 64,
        frontier_report_sha256="4" * 64,
        stage_a_comparisons=stage_a,
        stage_a_verdict="REPRODUCIBLE_LOCALIZATION_GAIN",
        stage_b_comparisons=stage_b,
        stage_b_advanced=True,
        stage_b_verdict="BALANCED_PROMISING",
    )

    destination = write_balanced_report(tmp_path / "report.json", report)
    assert write_balanced_report(destination, report) == destination
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["canonical_sha256"] == report.identity
    assert payload["scope"] == "test_public-only"
    assert payload["submitted"] is False
    serialized = destination.read_text(encoding="utf-8")
    assert "prediction" not in serialized
    assert "private" not in serialized


def test_stage_b_followups_are_conditional_on_the_fixed_probe_gate() -> None:
    _, config_640, config_576 = _configs()
    specs = build_candidate_specs(config_640, config_576, dataset_manifest_sha256="c" * 64)

    assert (
        select_followup_specs(specs, probe=_comparison(0.03, image_delta=-0.005, pixel_delta=0.001))
        == specs[3:]
    )
    assert (
        select_followup_specs(specs, probe=_comparison(0.03, image_delta=-0.02, pixel_delta=0.001))
        == ()
    )


def test_stage_b_probe_report_is_resumable_after_stage_a_resource_failure(
    tmp_path: Path,
) -> None:
    comparison = _comparison(0.03, image_delta=-0.005, pixel_delta=0.001)
    report = StageBProbeReport(
        source_sha="d" * 40,
        dataset_manifest_sha256="e" * 64,
        baseline_benchmark_sha256="f" * 64,
        baseline_config_sha256="1" * 64,
        config_576_sha256="2" * 64,
        stage_a_verdict="RESOURCE_LIMIT_EXCEEDED",
        stage_a_interruption_count=2,
        comparison=comparison,
    )

    destination = write_stage_b_probe_report(tmp_path / "probe.json", report)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["canonical_sha256"] == report.identity
    assert payload["advance"] is True
    assert payload["scope"] == "test_public-only"
    assert payload["submitted"] is False
    assert "private" not in destination.read_text(encoding="utf-8")
