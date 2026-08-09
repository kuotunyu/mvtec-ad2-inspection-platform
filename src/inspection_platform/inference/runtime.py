from __future__ import annotations

from typing import Protocol

from inspection_platform.contracts.models import ModelBundleManifest
from inspection_platform.contracts.predictions import PredictionRecord

from .mock import IncompatibleBundleError, LoadedMockModel, MockRuntime


class LoadedModel(Protocol):
    def predict(self, image: bytes, *, input_id: str) -> PredictionRecord: ...


class InferenceRuntime:
    """Lazy serving boundary; model engines are loaded only inside workers."""

    @staticmethod
    def load(manifest: ModelBundleManifest) -> LoadedModel:
        if manifest.runtime_kind == "mock":
            return MockRuntime.load(manifest)
        if manifest.runtime_kind != "anomalib":
            raise IncompatibleBundleError("unsupported runtime kind")
        # Real Anomalib loading is intentionally worker-only and requires an
        # exported bundle with adapter metadata; API startup never imports it.
        raise IncompatibleBundleError(
            "anomalib serving requires a verified worker bundle with adapter metadata"
        )


__all__ = ["InferenceRuntime", "LoadedModel"]
