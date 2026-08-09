from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from inspection_platform.contracts.models import ModelBundleManifest
from inspection_platform.contracts.predictions import PredictionRecord

from .mock import IncompatibleBundleError

InferencerFactory = Callable[[Path, str], Any]


def _default_factory(path: Path, device: str) -> Any:
    from anomalib.deploy import TorchInferencer

    return TorchInferencer(path=path, device=device)


@dataclass(frozen=True)
class LoadedAnomalibModel:
    manifest: ModelBundleManifest
    inferencer: Any
    decode_images: bool = True

    def predict(self, image: bytes, *, input_id: str) -> PredictionRecord:
        value: object = Image.open(BytesIO(image)) if self.decode_images else image
        result = self.inferencer.predict(value)
        score = float(np.asarray(result.pred_score).reshape(-1)[0])
        anomaly_map = np.asarray(result.anomaly_map, dtype=np.float32)
        return PredictionRecord(
            input_id=input_id,
            input_sha256=hashlib.sha256(image).hexdigest(),
            category=self.manifest.category,
            anomaly_score=score,
            anomaly_map_sha256=hashlib.sha256(anomaly_map.tobytes()).hexdigest(),
            model_bundle_id=self.manifest.identity,
        )


class AnomalibRuntime:
    @staticmethod
    def load(
        manifest: ModelBundleManifest,
        bundle_root: Path,
        *,
        device: str = "cpu",
        inferencer_factory: InferencerFactory | None = None,
    ) -> LoadedAnomalibModel:
        if manifest.runtime_kind != "anomalib" or manifest.model_family is None:
            raise IncompatibleBundleError("anomalib runtime requires a real model family")
        if manifest.prediction_contract_version != "1.0.0":
            raise IncompatibleBundleError("unsupported prediction contract")
        if manifest.preprocessing_sha256 is None or manifest.threshold is None:
            raise IncompatibleBundleError("bundle lacks preprocessing or threshold provenance")
        torch_files = [item for item in manifest.files if item.path.endswith((".pt", ".pth"))]
        if len(torch_files) != 1:
            raise IncompatibleBundleError("bundle must contain exactly one Torch artifact")
        model_path = (bundle_root / torch_files[0].path).resolve(strict=True)
        root = bundle_root.resolve(strict=True)
        if not model_path.is_relative_to(root):
            raise IncompatibleBundleError("model path escapes bundle root")
        factory = inferencer_factory or _default_factory
        return LoadedAnomalibModel(
            manifest,
            factory(model_path, device),
            decode_images=inferencer_factory is None,
        )


__all__ = ["AnomalibRuntime", "LoadedAnomalibModel"]
