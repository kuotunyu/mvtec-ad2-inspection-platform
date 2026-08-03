from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from experiments.models.base import (
    AnomalyExperimentAdapter,
    ExportContext,
    FitContext,
    ModelConfig,
    PredictContext,
    RawPrediction,
)
from experiments.models.factory import create_adapter


def model_config(family: str = "patchcore") -> ModelConfig:
    return ModelConfig.model_validate(
        {
            "family": family,
            "anomalib_version": "2.5.0",
            "model_name": "Patchcore",
            "backbone": "wide_resnet50_2",
            "input_size": [256, 256],
            "batch_size": 1,
            "precision": "32-true",
            "trainer_limits": {"max_epochs": 1, "max_steps": None},
            "seed": None,
            "preprocessing": {
                "resize": [256, 256],
                "normalization": "none" if family == "efficient_ad" else "imagenet",
            },
            "checkpoint_policy": {"mode": "best", "save_top_k": 1},
            "export_mode": "torch",
            "family_options": {},
        }
    )


class FakeAdapter(AnomalyExperimentAdapter):
    family = "patchcore"

    def __init__(self, config: ModelConfig, *, reverse: bool = False) -> None:
        super().__init__(config)
        self.reverse = reverse

    def _fit_model(self, context: FitContext) -> Path:
        raise NotImplementedError

    def _predict_model(self, context: PredictContext) -> Sequence[RawPrediction]:
        predictions = [
            RawPrediction(
                input_path=image,
                anomaly_score=float(index + 1),
                anomaly_map=np.full((2, 2), index + 1, dtype=np.float32),
                device_latency_ms=float(index + 10),
            )
            for index, image in enumerate(context.images)
        ]
        if self.reverse:
            predictions.reverse()
        return predictions

    def _export_model(self, context: ExportContext) -> Sequence[Path]:
        raise NotImplementedError


@pytest.fixture
def sample_batch(tmp_path: Path) -> list[Path]:
    images = [tmp_path / "001.png", tmp_path / "002.png"]
    for index, image in enumerate(images):
        image.write_bytes(f"image-{index}".encode())
    return images


def test_prediction_artifact_preserves_input_order(
    sample_batch: list[Path], tmp_path: Path
) -> None:
    adapter = FakeAdapter(model_config())

    artifact = adapter.predict(
        PredictContext(
            category="can",
            images=tuple(sample_batch),
            split="test_public",
            output_dir=tmp_path / "predictions",
            model_bundle_id="bundle-001",
            device="cpu",
            expected_map_shapes=((2, 2), (2, 2)),
        )
    )

    assert [item.input_path for item in artifact.records] == sample_batch
    assert all(item.anomaly_map_sha256 for item in artifact.records)
    assert all(item.path.suffix == ".npy" for item in artifact.anomaly_maps)
    assert artifact.device_latency_ms == (10.0, 11.0)


def test_prediction_artifact_rejects_adapter_reordering(
    sample_batch: list[Path], tmp_path: Path
) -> None:
    adapter = FakeAdapter(model_config(), reverse=True)

    with pytest.raises(ValueError, match="input order"):
        adapter.predict(
            PredictContext(
                category="can",
                images=tuple(sample_batch),
                split="test_public",
                output_dir=tmp_path / "predictions",
                model_bundle_id="bundle-001",
                device="cpu",
                expected_map_shapes=((2, 2), (2, 2)),
            )
        )


def test_factory_rejects_unapproved_family() -> None:
    with pytest.raises(ValueError, match="approved model family"):
        create_adapter("ganomaly", config={})


@pytest.mark.parametrize(
    ("family", "class_name"),
    [
        ("patchcore", "PatchcoreAdapter"),
        ("efficient_ad", "EfficientAdAdapter"),
        ("dinomaly", "DinomalyAdapter"),
    ],
)
def test_factory_constructs_each_approved_adapter(family: str, class_name: str) -> None:
    adapter = create_adapter(family, model_config(family))

    assert type(adapter).__name__ == class_name
