from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from experiments.models.base import AnomalyExperimentAdapter, ModelConfig
from inspection_platform.contracts import ModelFamily

APPROVED_MODEL_FAMILIES = ("patchcore", "efficient_ad", "dinomaly")


def create_adapter(
    family: ModelFamily | str,
    config: ModelConfig | Mapping[str, Any],
) -> AnomalyExperimentAdapter:
    """Construct an approved adapter through the project's only model entry point."""

    if family not in APPROVED_MODEL_FAMILIES:
        raise ValueError(f"{family!r} is not an approved model family")
    checked_config = (
        config if isinstance(config, ModelConfig) else ModelConfig.model_validate(config)
    )
    if checked_config.family != family:
        raise ValueError("model config family does not match requested adapter family")

    if family == "patchcore":
        from experiments.models.patchcore import PatchcoreAdapter

        return PatchcoreAdapter(checked_config)
    if family == "efficient_ad":
        from experiments.models.efficient_ad import EfficientAdAdapter

        return EfficientAdAdapter(checked_config)

    from experiments.models.dinomaly import DinomalyAdapter

    return DinomalyAdapter(checked_config)
