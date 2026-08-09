from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from inspection_platform.contracts.models import BundleFile, ModelBundleManifest
from inspection_platform.inference.anomalib_runtime import AnomalibRuntime
from inspection_platform.inference.mock import IncompatibleBundleError, MockRuntime
from inspection_platform.inference.runtime import InferenceRuntime


def _manifest() -> ModelBundleManifest:
    return ModelBundleManifest(
        category="can",
        runtime_kind="mock",
        model_family=None,
        evaluation_scope="synthetic-ci-only",
        files=(BundleFile(path="weights.bin", sha256="0" * 64, size=1),),
    )


def test_mock_runtime_is_deterministic() -> None:
    loaded = MockRuntime.load(_manifest())
    image = b"image"
    first = loaded.predict(image, input_id="one")
    second = loaded.predict(image, input_id="one")
    assert first == second
    assert first.input_sha256 == hashlib.sha256(image).hexdigest()


def test_mock_runtime_rejects_wrong_contract() -> None:
    manifest = _manifest().model_copy(update={"prediction_contract_version": "9.0.0"})
    try:
        MockRuntime.load(manifest)
    except IncompatibleBundleError:
        pass
    else:
        raise AssertionError("incompatible contract must fail closed")


def test_anomalib_runtime_loads_lazily_and_normalizes_prediction(tmp_path: Path) -> None:
    model = tmp_path / "model.pt"
    model.write_bytes(b"model")
    manifest = ModelBundleManifest(
        category="can",
        runtime_kind="anomalib",
        model_family="patchcore",
        files=(
            BundleFile(
                path="model.pt",
                sha256=hashlib.sha256(b"model").hexdigest(),
                size=5,
            ),
        ),
        preprocessing_sha256="1" * 64,
        threshold=0.5,
    )

    class Result:
        pred_score = np.asarray([0.75], dtype=np.float32)
        anomaly_map = np.ones((4, 4), dtype=np.float32)

    class FakeInferencer:
        def predict(self, _image: object) -> Result:
            return Result()

    loaded = AnomalibRuntime.load(
        manifest, tmp_path, inferencer_factory=lambda _path, _device: FakeInferencer()
    )
    detailed = loaded.predict_with_map(b"not-decoded-by-fake", input_id="one")
    assert detailed.record.anomaly_score == 0.75
    assert detailed.record.category == "can"
    assert detailed.anomaly_map.shape == (4, 4)
    assert detailed.anomaly_map.dtype == np.float32


def test_product_runtime_loads_verified_anomalib_bundle(tmp_path: Path) -> None:
    model = tmp_path / "model.pt"
    model.write_bytes(b"model")
    manifest = ModelBundleManifest(
        category="can",
        runtime_kind="anomalib",
        model_family="patchcore",
        files=(
            BundleFile(
                path="model.pt",
                sha256=hashlib.sha256(b"model").hexdigest(),
                size=5,
            ),
        ),
        preprocessing_sha256="1" * 64,
        threshold=0.5,
    )

    class Result:
        pred_score = np.asarray([0.25], dtype=np.float32)
        anomaly_map = np.ones((4, 4), dtype=np.float32)

    class FakeInferencer:
        def predict(self, _image: object) -> Result:
            return Result()

    loaded = InferenceRuntime.load(
        manifest,
        tmp_path,
        device="cuda:0",
        inferencer_factory=lambda _path, device: FakeInferencer() if device == "cuda:0" else None,
    )
    assert loaded.predict(b"input", input_id="one").anomaly_score == 0.25
