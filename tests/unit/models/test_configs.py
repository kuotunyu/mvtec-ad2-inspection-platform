from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from experiments.models.base import ModelConfig, load_model_config

CONFIG_ROOT = Path("experiments/configs/models")


@pytest.mark.parametrize(
    ("family", "model_name", "backbone"),
    [
        ("patchcore", "Patchcore", "wide_resnet50_2"),
        ("efficient_ad", "EfficientAd", "small"),
        ("dinomaly", "Dinomaly", "dinov2reg_vit_base_14"),
    ],
)
def test_frozen_model_config_is_complete_and_canonical(
    family: str, model_name: str, backbone: str
) -> None:
    path = CONFIG_ROOT / f"{family}.yaml"

    first = load_model_config(path)
    second = load_model_config(path)

    assert first.family == family
    assert first.model_name == model_name
    assert first.backbone == backbone
    assert first.anomalib_version == "2.5.0"
    assert first.seed is None
    assert first.input_size == first.preprocessing.resize
    assert first.batch_size > 0
    assert first.trainer_limits.max_epochs > 0
    assert first.checkpoint_policy.save_top_k == 1
    assert first.export_mode == "torch"
    assert first.identity == second.identity
    assert len(first.preprocessing_sha256) == 64


def test_model_config_requires_runtime_seed_injection() -> None:
    payload = load_model_config(CONFIG_ROOT / "patchcore.yaml").model_dump(
        mode="python", exclude_computed_fields=True
    )
    payload["seed"] = 42

    with pytest.raises(ValidationError, match="seed"):
        ModelConfig.model_validate(payload)
