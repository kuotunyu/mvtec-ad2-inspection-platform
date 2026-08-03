from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from experiments.models.base import AnomalibEngineAdapter


class EfficientAdAdapter(AnomalibEngineAdapter):
    """Project adapter for Anomalib EfficientAD."""

    family = "efficient_ad"

    def model_kwargs(self, auxiliary_data_roots: Mapping[str, Path]) -> dict[str, object]:
        imagenette = auxiliary_data_roots.get("imagenette")
        if imagenette is None:
            raise ValueError("EfficientAD requires an external imagenette data root")
        options = self.config.family_options
        return {
            "imagenet_dir": imagenette,
            "lr": options["lr"],
            "model_size": options["model_size"],
            "pad_maps": options["pad_maps"],
            "padding": options["padding"],
            "weight_decay": options["weight_decay"],
        }

    def _build_model(self, auxiliary_data_roots: Mapping[str, Path]) -> Any:
        from anomalib.models import EfficientAd

        pre_processor = EfficientAd.configure_pre_processor(
            image_size=self.config.preprocessing.resize
        )
        kwargs = self.model_kwargs(auxiliary_data_roots)
        return EfficientAd(
            imagenet_dir=cast(Path, kwargs["imagenet_dir"]),
            model_size=cast(str, kwargs["model_size"]),
            lr=cast(float, kwargs["lr"]),
            weight_decay=cast(float, kwargs["weight_decay"]),
            padding=cast(bool, kwargs["padding"]),
            pad_maps=cast(bool, kwargs["pad_maps"]),
            pre_processor=pre_processor,
        )
