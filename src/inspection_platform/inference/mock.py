from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFilter, ImageOps

from inspection_platform.contracts.models import ModelBundleManifest
from inspection_platform.contracts.predictions import PredictionRecord


class IncompatibleBundleError(ValueError):
    """Raised when a bundle cannot satisfy the prediction contract."""


@dataclass(frozen=True)
class MockPrediction:
    record: PredictionRecord
    anomaly_map: Image.Image


@dataclass(frozen=True)
class LoadedMockModel:
    manifest: ModelBundleManifest

    def _record(self, image: bytes, *, input_id: str, map_hash: str) -> PredictionRecord:
        input_hash = hashlib.sha256(image).hexdigest()
        score = int(input_hash[:8], 16) / 0xFFFFFFFF
        return PredictionRecord(
            input_id=input_id,
            input_sha256=input_hash,
            category=self.manifest.category,
            anomaly_score=score,
            anomaly_map_sha256=map_hash,
            model_bundle_id=self.manifest.identity,
        )

    def predict(self, image: bytes, *, input_id: str) -> PredictionRecord:
        input_hash = hashlib.sha256(image).hexdigest()
        map_hash = hashlib.sha256((self.manifest.identity + input_hash).encode()).hexdigest()
        return self._record(image, input_id=input_id, map_hash=map_hash)

    def predict_with_map(self, image: bytes, *, input_id: str) -> MockPrediction:
        with Image.open(BytesIO(image)) as decoded:
            anomaly_map = ImageOps.grayscale(decoded).filter(ImageFilter.FIND_EDGES).copy()
        map_hash = hashlib.sha256(anomaly_map.tobytes()).hexdigest()
        return MockPrediction(
            record=self._record(image, input_id=input_id, map_hash=map_hash),
            anomaly_map=anomaly_map,
        )


class MockRuntime:
    @staticmethod
    def load(manifest: ModelBundleManifest) -> LoadedMockModel:
        if manifest.runtime_kind != "mock" or manifest.evaluation_scope != "synthetic-ci-only":
            raise IncompatibleBundleError("mock runtime requires synthetic-ci-only bundle")
        if manifest.prediction_contract_version != "1.0.0":
            raise IncompatibleBundleError("unsupported prediction contract")
        return LoadedMockModel(manifest)


__all__ = ["IncompatibleBundleError", "LoadedMockModel", "MockPrediction", "MockRuntime"]
