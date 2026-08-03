from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from experiments.evaluate_public import (
    PublicGateError,
    PublicRunMetrics,
    compute_public_run_metrics,
    freeze_screening_stage,
    open_public_gate,
    verify_public_gate,
    write_frozen_stage,
)
from experiments.orchestration.queue import ExperimentStage, expand_stage
from experiments.orchestration.supervisor import RunStore
from experiments.run_matrix import PRE_GATE_PREDICTION_SPLITS
from inspection_platform.contracts import RunSpec


def screening_specs() -> list[RunSpec]:
    configs = {
        family: {"family": family, "batch_size": 1, "oom_fallback_batch_size": None}
        for family in ("patchcore", "efficient_ad", "dinomaly")
    }
    return expand_stage(
        ExperimentStage.model_validate(
            {
                "name": "screening",
                "family_configs": configs,
                "dataset_manifest_sha256": "a" * 64,
            }
        )
    )


def completed_store(root: Path) -> tuple[RunStore, list[RunSpec]]:
    store = RunStore(root)
    specs = screening_specs()
    for spec in specs:
        store.write_completed(spec, valid_artifacts=True)
    return store, specs


def test_gate_requires_all_24_hash_valid_screening_runs(tmp_path: Path) -> None:
    store, specs = completed_store(tmp_path / "runs")
    missing = specs[-1]
    store.quarantine(missing)

    with pytest.raises(PublicGateError, match="24 completed"):
        freeze_screening_stage(store, specs, experiment_version="v1")


def test_training_worker_cannot_predict_public_before_gate() -> None:
    assert PRE_GATE_PREDICTION_SPLITS == ("validation",)


def test_public_gate_is_idempotent_for_exact_frozen_manifest(tmp_path: Path) -> None:
    store, specs = completed_store(tmp_path / "runs")
    frozen = freeze_screening_stage(store, specs, experiment_version="v1")
    stage_path = write_frozen_stage(tmp_path / "screening-stage.json", frozen)
    gate_path = tmp_path / "public-gate.json"

    first = open_public_gate(stage_path, gate_path, clock=lambda: 123.5)
    second = open_public_gate(stage_path, gate_path, clock=lambda: 999.0)

    assert first == second
    assert first.opened_at == 123.5
    verify_public_gate(stage_path, gate_path)


def test_gate_rejects_any_post_open_stage_manifest_change(tmp_path: Path) -> None:
    store, specs = completed_store(tmp_path / "runs")
    frozen = freeze_screening_stage(store, specs, experiment_version="v1")
    stage_path = write_frozen_stage(tmp_path / "screening-stage.json", frozen)
    gate_path = tmp_path / "public-gate.json"
    open_public_gate(stage_path, gate_path, clock=lambda: 123.5)
    stage_path.write_text(stage_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(PublicGateError, match="changed after the public gate"):
        verify_public_gate(stage_path, gate_path)


def test_public_metrics_freeze_quality_operating_point_and_gpu_latency() -> None:
    masks = np.array(
        [
            [[False, False], [False, False]],
            [[True, False], [False, False]],
        ],
        dtype=np.bool_,
    )
    maps = np.array(
        [
            [[0.1, 0.2], [0.3, 0.4]],
            [[0.9, 0.1], [0.2, 0.3]],
        ],
        dtype=np.float64,
    )

    metrics = compute_public_run_metrics(
        labels=np.array([0, 1], dtype=np.int64),
        scores=np.array([0.5, 0.9], dtype=np.float64),
        masks=masks,
        maps=maps,
        threshold=0.5,
        device_latency_ms=(8.0, 12.0),
        setup_latency_ms=100.0,
        peak_vram_mib=512.0,
        artifact_size_bytes=1_024,
    )

    assert isinstance(metrics, PublicRunMetrics)
    assert metrics.image.auroc == 1.0
    assert metrics.operating.public_normal_false_review_rate == 1.0
    assert metrics.operating.public_anomaly_recall == 1.0
    assert metrics.gpu_latency.p50_ms == 10.0
    assert metrics.gpu_latency.p95_ms == pytest.approx(11.8)
    assert metrics.gpu_latency.throughput_images_per_second == 100.0
