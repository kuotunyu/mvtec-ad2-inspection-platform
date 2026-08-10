from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.high_resolution_patchcore import StudyMetrics, build_comparison
from experiments.memory_bounded_patchcore import (
    CandidateOutcome,
    MemoryBoundedStudyReport,
    build_candidate_specs,
    build_dry_run_payload,
    classify_memory_bounded_study,
    passes_seed42_gate,
    select_next_specs,
    select_ratio,
    validate_memory_bounded_config,
    write_memory_bounded_report,
)
from experiments.models.base import load_model_config


def _metrics(
    *,
    au_pro: float,
    image_auroc: float,
    pixel_auroc: float,
    artifact_mib: int = 150,
    p95_ms: float = 110.0,
) -> StudyMetrics:
    return StudyMetrics(
        au_pro=au_pro,
        image_auroc=image_auroc,
        pixel_auroc=pixel_auroc,
        gpu_p95_latency_ms=p95_ms,
        peak_vram_mib=18_000.0,
        artifact_size_bytes=artifact_mib * 1024**2,
        per_image_failure_rate=0.0,
    )


def _outcome(
    *,
    ratio: float = 0.01,
    seed: int = 42,
    au_pro_delta: float = 0.055,
    image_delta: float = -0.04,
    pixel_delta: float = 0.017,
    artifact_mib: int = 150,
    p95_ms: float = 110.0,
    resource_ok: bool = True,
) -> CandidateOutcome:
    baseline = _metrics(au_pro=0.53, image_auroc=0.57, pixel_auroc=0.914)
    candidate = _metrics(
        au_pro=baseline.au_pro + au_pro_delta,
        image_auroc=baseline.image_auroc + image_delta,
        pixel_auroc=baseline.pixel_auroc + pixel_delta,
        artifact_mib=artifact_mib,
        p95_ms=p95_ms,
    )
    comparison = build_comparison(
        category="wallplugs",
        baseline_run_identity="a" * 64,
        candidate_run_identity=f"{int(ratio * 1000) * 10_000 + seed:064x}",
        baseline=baseline,
        candidate=candidate,
        candidate_duration_seconds=600.0,
    )
    frontier_reference = (
        _metrics(
            au_pro=0.5981168894764237,
            image_auroc=0.532037037037037,
            pixel_auroc=0.931085743010617,
            artifact_mib=1194,
            p95_ms=166.7,
        )
        if seed == 42
        else None
    )
    return CandidateOutcome(
        ratio=ratio,
        seed=seed,
        comparison=comparison,
        frontier_reference=frontier_reference,
        resource_ok=resource_ok,
        resource_reason_sha256=None if resource_ok else "f" * 64,
    )


def _configs():
    reference = load_model_config(Path("experiments/configs/research/patchcore-640.yaml"))
    one = load_model_config(Path("experiments/configs/research/patchcore-640-coreset-001.yaml"))
    two = load_model_config(Path("experiments/configs/research/patchcore-640-coreset-002.yaml"))
    return reference, one, two


def test_ratio_configs_change_only_the_declared_coreset_ratio() -> None:
    reference, one, two = _configs()

    validate_memory_bounded_config(one, reference=reference, ratio=0.01)
    validate_memory_bounded_config(two, reference=reference, ratio=0.02)

    payload = one.model_dump(mode="json", exclude_computed_fields=True)
    assert payload["family_options"]["coreset_sampling_ratio"] == 0.01  # type: ignore[index]


def test_config_guard_rejects_an_unapproved_change() -> None:
    reference, one, _ = _configs()
    payload = one.model_dump(mode="json", exclude_computed_fields=True)
    payload["family_options"]["num_neighbors"] = 1  # type: ignore[index]

    with pytest.raises(ValueError, match="only coreset_sampling_ratio"):
        validate_memory_bounded_config(
            type(one).model_validate(payload), reference=reference, ratio=0.01
        )


def test_candidate_specs_freeze_ratio_then_seed_order() -> None:
    _, one, two = _configs()

    specs = build_candidate_specs(one, two, dataset_manifest_sha256="a" * 64)

    assert [
        (spec.config["family_options"]["coreset_sampling_ratio"], spec.seed)  # type: ignore[index]
        for spec in specs
    ] == [
        (0.01, 42),
        (0.02, 42),
        (0.01, 17),
        (0.01, 2026),
        (0.02, 17),
        (0.02, 2026),
    ]


def test_ratio_one_advances_when_quality_and_efficiency_are_preserved() -> None:
    outcome = _outcome()

    assert passes_seed42_gate(outcome)
    assert select_ratio((outcome,)) == 0.01


def test_ratio_two_is_allowed_only_after_a_safe_quality_miss() -> None:
    _, one, two = _configs()
    specs = build_candidate_specs(one, two, dataset_manifest_sha256="a" * 64)
    miss = _outcome(au_pro_delta=0.01)
    rescue = _outcome(ratio=0.02, artifact_mib=250)

    assert select_next_specs(specs, probes=(miss,)) == (specs[1],)
    assert select_ratio((miss, rescue)) == 0.02
    assert select_next_specs(specs, probes=(_outcome(resource_ok=False),)) == ()


def test_first_passing_ratio_selects_only_its_replication_specs() -> None:
    _, one, two = _configs()
    specs = build_candidate_specs(one, two, dataset_manifest_sha256="a" * 64)

    assert select_next_specs(specs, probes=(_outcome(),)) == specs[2:4]
    assert (
        select_next_specs(
            specs,
            probes=(_outcome(au_pro_delta=0.01), _outcome(ratio=0.02, artifact_mib=250)),
        )
        == specs[4:6]
    )


def test_three_seed_verdict_is_recomputed() -> None:
    outcomes = (
        _outcome(seed=42, au_pro_delta=0.04),
        _outcome(seed=17, au_pro_delta=0.03, image_delta=-0.03),
        _outcome(seed=2026, au_pro_delta=0.01, image_delta=-0.04),
    )

    assert classify_memory_bounded_study(outcomes) == "EFFICIENT_REPRODUCIBLE"
    assert (
        classify_memory_bounded_study(
            (outcomes[0], outcomes[1], _outcome(seed=2026, au_pro_delta=-0.08))
        )
        == "EFFICIENT_SEED42_ONLY"
    )
    assert (
        classify_memory_bounded_study(
            (outcomes[0], outcomes[1], _outcome(seed=2026, resource_ok=False))
        )
        == "RESOURCE_LIMIT_EXCEEDED"
    )


def _report() -> MemoryBoundedStudyReport:
    probe = _outcome()
    replications = (
        _outcome(seed=17, au_pro_delta=0.03, image_delta=-0.03),
        _outcome(seed=2026, au_pro_delta=0.01, image_delta=-0.04),
    )
    return MemoryBoundedStudyReport(
        source_sha="1" * 40,
        dataset_manifest_sha256="2" * 64,
        baseline_benchmark_sha256="3" * 64,
        baseline_config_sha256="4" * 64,
        reference_config_sha256="5" * 64,
        config_001_sha256="6" * 64,
        config_002_sha256="7" * 64,
        frontier_report_sha256="8" * 64,
        probes=(probe,),
        selected_ratio=0.01,
        replications=replications,
        verdict="EFFICIENT_REPRODUCIBLE",
    )


def test_report_recomputes_branching_verdict_and_identity(tmp_path: Path) -> None:
    report = _report()

    destination = write_memory_bounded_report(tmp_path / "report.json", report)
    assert write_memory_bounded_report(destination, report) == destination
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["canonical_sha256"] == report.identity
    assert payload["scope"] == "test_public-only"
    assert payload["submitted"] is False
    assert payload["champions_changed"] is False
    assert payload["selected_ratio"] == 0.01
    serialized = destination.read_text(encoding="utf-8").lower()
    for forbidden in ("prediction", "private", "password", "token", "path"):
        assert forbidden not in serialized


def test_report_rejects_unfrozen_selected_ratio_or_replication_branch() -> None:
    payload = _report().model_dump(mode="json", exclude_computed_fields=True)
    payload["selected_ratio"] = 0.02
    with pytest.raises(ValueError, match="selected ratio"):
        MemoryBoundedStudyReport.model_validate(payload)

    payload = _report().model_dump(mode="json", exclude_computed_fields=True)
    payload["replications"] = []
    with pytest.raises(ValueError, match="replication"):
        MemoryBoundedStudyReport.model_validate(payload)


def test_dry_run_payload_binds_fixed_identities_and_conditional_rule() -> None:
    reference, one, two = _configs()
    specs = build_candidate_specs(one, two, dataset_manifest_sha256="a" * 64)

    payload = build_dry_run_payload(
        specs=specs,
        source_sha="b" * 40,
        dataset_manifest_sha256="a" * 64,
        reference_config_sha256=reference.identity,
        config_001_sha256=one.identity,
        config_002_sha256=two.identity,
        baseline_benchmark_sha256="c" * 64,
        frontier_report_sha256="d" * 64,
    )

    assert payload["identities"] == [spec.identity for spec in specs]
    assert payload["conditional_rule"] == (
        "probe-0.01; rescue-0.02-only-after-safe-quality-miss; replicate-first-passing-ratio"
    )
    assert payload["source_sha"] == "b" * 40
