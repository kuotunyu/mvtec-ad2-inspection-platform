from __future__ import annotations

import hashlib

from inspection_platform.contracts.models import BundleFile, ModelBundleManifest
from inspection_platform.inference.mock import IncompatibleBundleError, MockRuntime


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
