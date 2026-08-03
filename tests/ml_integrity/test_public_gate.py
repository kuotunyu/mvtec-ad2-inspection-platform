from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from experiments.evaluate_public import (
    PublicGateError,
    PublicRunMetrics,
    _metric_arrays,
    _restore_preprocessing_geometry,
    compute_public_run_metrics,
    freeze_screening_stage,
    open_public_gate,
    verify_public_gate,
    write_frozen_stage,
)
from experiments.models.base import ArtifactFile, PredictionArtifact, PreprocessingConfig
from experiments.orchestration.queue import ExperimentStage, expand_stage
from experiments.orchestration.supervisor import RunStore
from experiments.run_matrix import PRE_GATE_PREDICTION_SPLITS
from inspection_platform.contracts import PredictionRecord, RunSpec, sha256_file


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


def test_metric_arrays_restore_center_crop_to_full_frame(tmp_path: Path) -> None:
    image_path = tmp_path / "can" / "test_public" / "bad" / "000.png"
    mask_path = tmp_path / "can" / "test_public" / "ground_truth" / "bad" / "000_mask.png"
    map_path = tmp_path / "000.npy"
    image_path.parent.mkdir(parents=True)
    mask_path.parent.mkdir(parents=True)
    Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8)).save(image_path)
    Image.fromarray(np.zeros((4, 4), dtype=np.uint8)).save(mask_path)
    np.save(map_path, np.array([[1.0, 1.0], [1.0, 0.0]], dtype=np.float32))
    map_sha256 = sha256_file(map_path)
    artifact = PredictionArtifact(
        family="dinomaly",
        category="can",
        split="test_public",
        config_sha256="a" * 64,
        records=(
            PredictionRecord(
                input_id="000:000.png",
                input_sha256=sha256_file(image_path),
                category="can",
                anomaly_score=1.0,
                anomaly_map_sha256=map_sha256,
                model_bundle_id="run:test",
                input_path=image_path,
            ),
        ),
        anomaly_maps=(
            ArtifactFile(path=map_path, sha256=map_sha256, size=map_path.stat().st_size),
        ),
    )

    _, _, _, maps = _metric_arrays(
        artifact,
        preprocessing=PreprocessingConfig(
            resize=(4, 4),
            center_crop=(2, 2),
            normalization="imagenet",
        ),
        evaluation_size=(4, 4),
    )

    np.testing.assert_array_equal(
        maps,
        np.array(
            [
                [
                    [0.0, 0.0, 0.0, 0.0],
                    [0.0, 1.0, 1.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0],
                ]
            ],
            dtype=np.float64,
        ),
    )


def test_geometry_restore_rejects_map_outside_frozen_preprocessing_shape() -> None:
    preprocessing = PreprocessingConfig(
        resize=(4, 4),
        center_crop=(2, 2),
        normalization="imagenet",
    )

    with pytest.raises(PublicGateError, match="frozen preprocessing shape"):
        _restore_preprocessing_geometry(
            np.zeros((1, 2), dtype=np.float32),
            preprocessing,
            (4, 4),
        )
