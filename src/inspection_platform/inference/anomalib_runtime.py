from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from inspection_platform.contracts.models import ModelBundleManifest
from inspection_platform.contracts.predictions import PredictionRecord

from .mock import IncompatibleBundleError

InferencerFactory = Callable[[Path, str], Any]


def _normalize_inferencer_device(device: str) -> str:
    if device.startswith("cuda:") and device.removeprefix("cuda:").isdigit():
        return "cuda"
    return device


@contextmanager
def _trusted_remote_code_scope() -> Iterator[None]:
    previous = os.environ.get("TRUST_REMOTE_CODE")
    os.environ["TRUST_REMOTE_CODE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TRUST_REMOTE_CODE", None)
        else:
            os.environ["TRUST_REMOTE_CODE"] = previous


def _default_factory(path: Path, device: str) -> Any:
    from anomalib.deploy import TorchInferencer

    with _trusted_remote_code_scope():
        return TorchInferencer(path=path, device=_normalize_inferencer_device(device))


@dataclass(frozen=True)
class AnomalibPrediction:
    record: PredictionRecord
    anomaly_map: NDArray[np.float32]


@dataclass(frozen=True)
class LoadedAnomalibModel:
    manifest: ModelBundleManifest
    inferencer: Any
    decode_images: bool = True

    def predict(self, image: bytes, *, input_id: str) -> PredictionRecord:
        return self.predict_with_map(image, input_id=input_id).record

    def predict_with_map(self, image: bytes, *, input_id: str) -> AnomalibPrediction:
        value: object = Image.open(BytesIO(image)) if self.decode_images else image
        result = self.inferencer.predict(value)
        score = float(np.asarray(result.pred_score).reshape(-1)[0])
        anomaly_map = np.asarray(result.anomaly_map, dtype=np.float32).squeeze()
        if anomaly_map.ndim != 2 or not np.isfinite(anomaly_map).all():
            raise ValueError("anomalib runtime produced an invalid anomaly map")
        return AnomalibPrediction(
            record=PredictionRecord(
                input_id=input_id,
                input_sha256=hashlib.sha256(image).hexdigest(),
                category=self.manifest.category,
                anomaly_score=score,
                anomaly_map_sha256=hashlib.sha256(anomaly_map.tobytes()).hexdigest(),
                model_bundle_id=self.manifest.identity,
            ),
            anomaly_map=anomaly_map,
        )


class AnomalibRuntime:
    @staticmethod
    def load(
        manifest: ModelBundleManifest,
        bundle_root: Path,
        *,
        device: str = "cpu",
        inferencer_factory: InferencerFactory | None = None,
        trust_verified_bundle: bool = False,
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
        if inferencer_factory is None and not trust_verified_bundle:
            raise IncompatibleBundleError("real inference requires explicit verified bundle trust")
        factory = inferencer_factory or _default_factory
        return LoadedAnomalibModel(
            manifest,
            factory(model_path, device),
            decode_images=inferencer_factory is None,
        )


__all__ = ["AnomalibPrediction", "AnomalibRuntime", "LoadedAnomalibModel"]
