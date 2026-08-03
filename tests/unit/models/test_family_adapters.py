from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.models.base import AdapterContractError, AnomalibEngineAdapter, load_model_config
from experiments.models.dinomaly import DinomalyAdapter
from experiments.models.efficient_ad import EfficientAdAdapter
from experiments.models.patchcore import PatchcoreAdapter

CONFIG_ROOT = Path("experiments/configs/models")


def test_patchcore_compatibility_translation_is_frozen() -> None:
    adapter = PatchcoreAdapter(load_model_config(CONFIG_ROOT / "patchcore.yaml"))

    assert adapter.model_kwargs({}) == {
        "backbone": "wide_resnet50_2",
        "coreset_sampling_ratio": 0.1,
        "layers": ("layer2", "layer3"),
        "num_neighbors": 9,
        "precision": "float32",
    }


def test_efficient_ad_compatibility_translation_requires_external_imagenette(
    tmp_path: Path,
) -> None:
    adapter = EfficientAdAdapter(load_model_config(CONFIG_ROOT / "efficient_ad.yaml"))
    imagenette = tmp_path / "imagenette"

    assert adapter.model_kwargs({"imagenette": imagenette}) == {
        "imagenet_dir": imagenette,
        "lr": 0.0001,
        "model_size": "small",
        "pad_maps": True,
        "padding": False,
        "weight_decay": 0.00001,
    }
    with pytest.raises(ValueError, match="imagenette"):
        adapter.model_kwargs({})


def test_dinomaly_compatibility_translation_is_frozen() -> None:
    adapter = DinomalyAdapter(load_model_config(CONFIG_ROOT / "dinomaly.yaml"))

    assert adapter.model_kwargs({}) == {
        "bottleneck_dropout": 0.0,
        "decoder_depth": 8,
        "encoder_name": "dinov2reg_vit_base_14",
        "precision": "float32",
    }


def test_checkpoint_selection_honors_frozen_policy() -> None:
    adapter = PatchcoreAdapter(load_model_config(CONFIG_ROOT / "patchcore.yaml"))
    callback = SimpleNamespace(
        best_model_path="artifacts/best.ckpt",
        last_model_path="artifacts/last.ckpt",
    )

    assert adapter._checkpoint_candidate(callback) == Path("artifacts/best.ckpt")


def test_trainer_device_preserves_requested_cuda_index() -> None:
    assert AnomalibEngineAdapter._trainer_device("cpu") == ("cpu", 1)
    assert AnomalibEngineAdapter._trainer_device("cuda:2") == ("gpu", [2])
    with pytest.raises(AdapterContractError, match="device"):
        AnomalibEngineAdapter._trainer_device("cuda")
