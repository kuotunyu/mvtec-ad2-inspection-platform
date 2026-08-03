from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from experiments.models.base import AnomalibEngineAdapter


class DinomalyAdapter(AnomalibEngineAdapter):
    """Project adapter for Anomalib Dinomaly."""

    family = "dinomaly"

    def model_kwargs(self, auxiliary_data_roots: Mapping[str, Path]) -> dict[str, object]:
        del auxiliary_data_roots
        options = self.config.family_options
        return {
            "bottleneck_dropout": options["bottleneck_dropout"],
            "decoder_depth": options["decoder_depth"],
            "encoder_name": options["encoder_name"],
            "precision": "float32",
        }

    def _build_model(self, auxiliary_data_roots: Mapping[str, Path]) -> Any:
        from anomalib.models import Dinomaly

        crop = self.config.preprocessing.center_crop
        if crop is None or crop[0] != crop[1]:
            raise ValueError("Dinomaly requires a square center_crop")
        pre_processor = Dinomaly.configure_pre_processor(
            image_size=self.config.preprocessing.resize,
            crop_size=crop[0],
        )
        kwargs = self.model_kwargs(auxiliary_data_roots)
        return Dinomaly(
            encoder_name=cast(str, kwargs["encoder_name"]),
            bottleneck_dropout=cast(float, kwargs["bottleneck_dropout"]),
            decoder_depth=cast(int, kwargs["decoder_depth"]),
            precision=cast(str, kwargs["precision"]),
            pre_processor=pre_processor,
        )
