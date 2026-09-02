from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from experiments.evaluate_public import load_public_benchmark
from experiments.high_resolution_patchcore import (
    CANDIDATE_RESOLUTION,
    STUDY_CATEGORIES,
    HighResolutionStudyReport,
    StudyFailure,
    StudyMetrics,
    build_comparison,
    build_study_specs,
    classify_study,
    select_baseline_runs,
    validate_candidate_config,
    validate_external_paths,
    write_study_report,
)
from experiments.models.base import ModelConfig, load_model_config


def _candidate_config() -> ModelConfig:
    baseline = load_model_config(Path("experiments/configs/models/patchcore.yaml"))
    payload = baseline.model_dump(mode="json", exclude_computed_fields=True)
    payload["input_size"] = list(CANDIDATE_RESOLUTION)
    preprocessing = deepcopy(payload["preprocessing"])
    assert isinstance(preprocessing, dict)
    preprocessing["resize"] = list(CANDIDATE_RESOLUTION)
    payload["preprocessing"] = preprocessing
    return ModelConfig.model_validate(payload)


def test_study_specs_are_fixed_to_two_768_seed_42_patchcore_runs() -> None:
    baseline = load_model_config(Path("experiments/configs/models/patchcore.yaml"))
    candidate = _candidate_config()

    validate_candidate_config(candidate, baseline=baseline)
    specs = build_study_specs(candidate, dataset_manifest_sha256="a" * 64)

    assert tuple(spec.category for spec in specs) == STUDY_CATEGORIES
    assert all(spec.model_family == "patchcore" for spec in specs)
    assert all(spec.seed == 42 for spec in specs)
    assert all(spec.config["input_size"] == [768, 768] for spec in specs)


def test_candidate_rejects_changes_beyond_input_geometry() -> None:
    baseline = load_model_config(Path("experiments/configs/models/patchcore.yaml"))
    payload = _candidate_config().model_dump(mode="json", exclude_computed_fields=True)
    options = deepcopy(payload["family_options"])
    assert isinstance(options, dict)
    options["coreset_sampling_ratio"] = 0.05
    payload["family_options"] = options

    with pytest.raises(ValueError, match=r"only input_size and preprocessing\.resize"):
        validate_candidate_config(ModelConfig.model_validate(payload), baseline=baseline)


def _metrics(
    au_pro: float,
    *,
    vram_mib: float = 4_000.0,
    p95_ms: float = 150.0,
    failure_rate: float = 0.0,
) -> StudyMetrics:
    return StudyMetrics(
        au_pro=au_pro,
        image_auroc=0.7,
        pixel_auroc=0.8,
        gpu_p95_latency_ms=p95_ms,
        peak_vram_mib=vram_mib,
        artifact_size_bytes=1_000,
        per_image_failure_rate=failure_rate,
    )


def _comparison(
    category: str,
    *,
    baseline_au_pro: float,
    candidate_au_pro: float,
    vram_mib: float = 4_000.0,
    p95_ms: float = 150.0,
    failure_rate: float = 0.0,
):
    return build_comparison(
        category=category,
        baseline_run_identity="a" * 64,
        candidate_run_identity=("b" if category == "can" else "c") * 64,
        baseline=_metrics(baseline_au_pro),
        candidate=_metrics(
            candidate_au_pro,
            vram_mib=vram_mib,
            p95_ms=p95_ms,
            failure_rate=failure_rate,
        ),
        candidate_duration_seconds=120.0,
    )


def test_baselines_are_exact_frozen_seed_42_patchcore_runs() -> None:
    benchmark = load_public_benchmark(Path("reports/public_benchmark.json"))
    baseline = load_model_config(Path("experiments/configs/models/patchcore.yaml"))

    selected = select_baseline_runs(benchmark, baseline_config=baseline)

    assert {category: run.run_identity for category, run in selected.items()} == {
        "can": "597dbe614d9aa98fd8939b0626aaf61def78fa4abac1b25755aeb5b5c980e81a",
        "wallplugs": "6ffd7c77dc95549ae174f324c19684a44a90808029672390c07cc72df9874972",
    }


@pytest.mark.parametrize(
    ("comparisons", "expected"),
    [
        (
            (
                _comparison("can", baseline_au_pro=0.30, candidate_au_pro=0.33),
                _comparison("wallplugs", baseline_au_pro=0.50, candidate_au_pro=0.50),
            ),
            "PROMISING",
        ),
        (
            (
                _comparison("can", baseline_au_pro=0.30, candidate_au_pro=0.33),
                _comparison("wallplugs", baseline_au_pro=0.50, candidate_au_pro=0.47),
            ),
            "MIXED",
        ),
        (
            (
                _comparison("can", baseline_au_pro=0.30, candidate_au_pro=0.31),
                _comparison("wallplugs", baseline_au_pro=0.50, candidate_au_pro=0.50),
            ),
            "NO_CLEAR_GAIN",
        ),
        (
            (
                _comparison(
                    "can",
                    baseline_au_pro=0.30,
                    candidate_au_pro=0.35,
                    vram_mib=12_289.0,
                ),
                _comparison("wallplugs", baseline_au_pro=0.50, candidate_au_pro=0.55),
            ),
            "RESOURCE_LIMIT_EXCEEDED",
        ),
    ],
)
def test_result_classification_is_frozen(comparisons, expected: str) -> None:
    assert classify_study(comparisons) == expected


def test_external_paths_reject_repository_outputs(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the repository"):
        validate_external_paths(
            repository=repository,
            runs_root=repository / "runs",
            output=tmp_path / "result.json",
        )

    with pytest.raises(ValueError, match="inside the runs root"):
        validate_external_paths(
            repository=repository,
            runs_root=tmp_path / "external-runs",
            output=tmp_path / "other" / "result.json",
        )


def test_report_is_identity_bound_and_contains_only_aggregate_public_evidence(
    tmp_path: Path,
) -> None:
    comparisons = (
        _comparison("can", baseline_au_pro=0.30, candidate_au_pro=0.33),
        _comparison("wallplugs", baseline_au_pro=0.50, candidate_au_pro=0.50),
    )
    report = HighResolutionStudyReport(
        source_sha="d" * 40,
        dataset_manifest_sha256="e" * 64,
        baseline_benchmark_sha256="f" * 64,
        baseline_config_sha256="1" * 64,
        candidate_config_sha256="2" * 64,
        comparisons=comparisons,
        verdict=classify_study(comparisons),
    )

    destination = write_study_report(tmp_path / "result.json", report)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["canonical_sha256"] == report.identity
    assert payload["scope"] == "test_public-only"
    assert payload["submitted"] is False
    assert payload["verdict"] == "PROMISING"
    assert "input_path" not in destination.read_text(encoding="utf-8")
    assert "prediction" not in destination.read_text(encoding="utf-8")


def test_failed_runs_freeze_a_sanitized_resource_limit_report(tmp_path: Path) -> None:
    failures = tuple(
        StudyFailure(
            category=category,
            candidate_run_identity=("a" if category == "can" else "b") * 64,
            code_revision=("4" if category == "can" else "5") * 40,
            candidate_duration_seconds=72.0,
            attempt=1,
            exit_code=1,
            error_kind="oom",
            error_sha256=("c" if category == "can" else "d") * 64,
        )
        for category in STUDY_CATEGORIES
    )
    report = HighResolutionStudyReport(
        source_sha="e" * 40,
        dataset_manifest_sha256="f" * 64,
        baseline_benchmark_sha256="1" * 64,
        baseline_config_sha256="2" * 64,
        candidate_config_sha256="3" * 64,
        comparisons=(),
        failures=failures,
        verdict="RESOURCE_LIMIT_EXCEEDED",
    )

    destination = write_study_report(tmp_path / "resource-limit.json", report)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["verdict"] == "RESOURCE_LIMIT_EXCEEDED"
    assert [item["category"] for item in payload["failures"]] == list(STUDY_CATEGORIES)
    assert all(item["error_kind"] == "oom" for item in payload["failures"])
    assert [item["code_revision"] for item in payload["failures"]] == ["4" * 40, "5" * 40]
    assert "OutOfMemoryError" not in destination.read_text(encoding="utf-8")


def test_committed_high_resolution_result_is_public_only_and_keeps_champions() -> None:
    destination = Path("reports/high_resolution_patchcore.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    claimed_identity = payload.pop("canonical_sha256")
    report = HighResolutionStudyReport.model_validate(payload)
    champions = json.loads(Path("reports/champions.json").read_text(encoding="utf-8"))

    assert report.identity == claimed_identity
    assert report.scope == "test_public-only"
    assert report.submitted is False
    assert report.verdict == "RESOURCE_LIMIT_EXCEEDED"
    assert report.comparisons == ()
    assert tuple(item.category for item in report.failures) == STUDY_CATEGORIES
    assert all(item.error_kind == "oom" for item in report.failures)
    assert champions["champions"]["can"] == "patchcore"
    assert champions["champions"]["wallplugs"] == "patchcore"


def test_committed_cloud_result_completed_but_failed_the_serving_gate() -> None:
    payload = json.loads(
        Path("reports/high_resolution_patchcore_cloud.json").read_text(encoding="utf-8")
    )
    claimed_identity = payload.pop("canonical_sha256")
    report = HighResolutionStudyReport.model_validate(payload)
    champions = json.loads(Path("reports/champions.json").read_text(encoding="utf-8"))

    assert report.identity == claimed_identity
    assert report.scope == "test_public-only"
    assert report.submitted is False
    assert report.verdict == "RESOURCE_LIMIT_EXCEEDED"
    assert report.failures == ()
    assert tuple(item.category for item in report.comparisons) == STUDY_CATEGORIES

    for comparison in report.comparisons:
        assert comparison.au_pro_delta > 0.02
        assert comparison.candidate.gpu_p95_latency_ms > 500.0
        assert comparison.candidate.peak_vram_mib < 12_288.0
        assert comparison.candidate.per_image_failure_rate == 0.0

    assert champions["champions"]["can"] == "patchcore"
    assert champions["champions"]["wallplugs"] == "patchcore"


def test_committed_4090_resource_limit_report_is_unchanged() -> None:
    payload = json.loads(Path("reports/high_resolution_patchcore.json").read_text(encoding="utf-8"))

    assert payload["canonical_sha256"] == (
        "2a54b716ca8782beae998222e7e39d1cd2168bcd63a0a3cc955d07c7fad70544"
    )
    assert payload["verdict"] == "RESOURCE_LIMIT_EXCEEDED"
    assert payload["comparisons"] == []
    assert [item["error_kind"] for item in payload["failures"]] == ["oom", "oom"]


def test_cloud_environment_sidecar_binds_to_its_study_report() -> None:
    report = json.loads(
        Path("reports/high_resolution_patchcore_cloud.json").read_text(encoding="utf-8")
    )
    sidecar = json.loads(
        Path("reports/high_resolution_patchcore_cloud_environment.json").read_text(encoding="utf-8")
    )

    assert sidecar["study_report_sha256"] == report["canonical_sha256"]
    assert sidecar["study"] == report["study"]
    assert sidecar["verdict"] == report["verdict"]
    assert sidecar["evaluation_scope"] == "test_public-only"
    assert sidecar["submitted"] is False
    assert sidecar["environment"]["gpu_name"] == "NVIDIA A100-SXM4-80GB"
    assert sidecar["environment"]["gpu_memory_mib"] == 81920

    peaks = sidecar["training_peak_vram_mib"]
    assert set(peaks) == set(STUDY_CATEGORIES)
    assert all(value > 24 * 1024 for value in peaks.values()), (
        "both fits must exceed the 24 GiB workstation that could not run this study"
    )
