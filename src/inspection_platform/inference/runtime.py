from __future__ import annotations

from pathlib import Path
from typing import Protocol

from inspection_platform.contracts.models import ModelBundleManifest
from inspection_platform.contracts.predictions import PredictionRecord

from .anomalib_runtime import AnomalibRuntime, InferencerFactory
from .mock import IncompatibleBundleError, MockRuntime


class LoadedModel(Protocol):
    def predict(self, image: bytes, *, input_id: str) -> PredictionRecord: ...


class InferenceRuntime:
    """Lazy serving boundary; model engines are loaded only inside workers."""

    @staticmethod
    def load(
        manifest: ModelBundleManifest,
        bundle_root: Path | None = None,
        *,
        device: str = "cpu",
        inferencer_factory: InferencerFactory | None = None,
    ) -> LoadedModel:
        if manifest.runtime_kind == "mock":
            return MockRuntime.load(manifest)
        if manifest.runtime_kind != "anomalib":
            raise IncompatibleBundleError("unsupported runtime kind")
        if bundle_root is None:
            raise IncompatibleBundleError("anomalib serving requires the verified bundle root")
        return AnomalibRuntime.load(
            manifest,
            bundle_root,
            device=device,
            inferencer_factory=inferencer_factory,
        )


__all__ = ["InferenceRuntime", "LoadedModel"]
