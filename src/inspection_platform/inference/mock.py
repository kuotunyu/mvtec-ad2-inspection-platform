from __future__ import annotations

import hashlib
from dataclasses import dataclass

from inspection_platform.contracts.models import ModelBundleManifest
from inspection_platform.contracts.predictions import PredictionRecord


class IncompatibleBundleError(ValueError):
    """Raised when a bundle cannot satisfy the prediction contract."""


@dataclass(frozen=True)
class LoadedMockModel:
    manifest: ModelBundleManifest

    def predict(self, image: bytes, *, input_id: str) -> PredictionRecord:
        input_hash = hashlib.sha256(image).hexdigest()
        score = int(input_hash[:8], 16) / 0xFFFFFFFF
        map_hash = hashlib.sha256((self.manifest.identity + input_hash).encode()).hexdigest()
        return PredictionRecord(
            input_id=input_id,
            input_sha256=input_hash,
            category=self.manifest.category,
            anomaly_score=score,
            anomaly_map_sha256=map_hash,
            model_bundle_id=self.manifest.identity,
        )


class MockRuntime:
    @staticmethod
    def load(manifest: ModelBundleManifest) -> LoadedMockModel:
        if manifest.runtime_kind != "mock" or manifest.evaluation_scope != "synthetic-ci-only":
            raise IncompatibleBundleError("mock runtime requires synthetic-ci-only bundle")
        if manifest.prediction_contract_version != "1.0.0":
            raise IncompatibleBundleError("unsupported prediction contract")
        return LoadedMockModel(manifest)


__all__ = ["IncompatibleBundleError", "LoadedMockModel", "MockRuntime"]
