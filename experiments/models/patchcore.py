from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from experiments.models.base import AnomalibEngineAdapter


class PatchcoreAdapter(AnomalibEngineAdapter):
    """Project adapter for Anomalib PatchCore."""

    family = "patchcore"

    def model_kwargs(self, auxiliary_data_roots: Mapping[str, Path]) -> dict[str, object]:
        del auxiliary_data_roots
        options = self.config.family_options
        layers = options.get("layers")
        if not isinstance(layers, list) or not all(isinstance(layer, str) for layer in layers):
            raise ValueError("PatchCore layers must be a string list")
        return {
            "backbone": self.config.backbone,
            "coreset_sampling_ratio": options["coreset_sampling_ratio"],
            "layers": tuple(layers),
            "num_neighbors": options["num_neighbors"],
            "precision": "float32",
        }

    def _build_model(self, auxiliary_data_roots: Mapping[str, Path]) -> Any:
        from anomalib.models import Patchcore

        pre_processor = Patchcore.configure_pre_processor(
            image_size=self.config.preprocessing.resize,
            center_crop_size=self.config.preprocessing.center_crop,
        )
        kwargs = self.model_kwargs(auxiliary_data_roots)
        return Patchcore(
            backbone=cast(str, kwargs["backbone"]),
            layers=cast(tuple[str, ...], kwargs["layers"]),
            coreset_sampling_ratio=cast(float, kwargs["coreset_sampling_ratio"]),
            num_neighbors=cast(int, kwargs["num_neighbors"]),
            precision=cast(str, kwargs["precision"]),
            pre_processor=pre_processor,
        )
