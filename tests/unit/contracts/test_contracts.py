from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from inspection_platform.contracts import (
    DatasetManifest,
    ModelBundleManifest,
    PredictionRecord,
    RunRecord,
    RunSpec,
    canonical_hash,
    sha256_file,
)


def test_run_spec_hash_is_order_independent() -> None:
    left = RunSpec(
        model_family="patchcore",
        category="can",
        seed=42,
        config={"a": 1, "b": 2},
    )
    right = RunSpec(
        model_family="patchcore",
        category="can",
        seed=42,
        config={"b": 2, "a": 1},
    )

    assert left.identity == right.identity
    assert left.identity == canonical_hash(left)


def test_run_spec_rejects_unapproved_model_family() -> None:
    with pytest.raises(ValidationError, match="model_family"):
        RunSpec(model_family="ganomaly", category="can", seed=42, config={})


def test_run_spec_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="unexpected"):
        RunSpec(
            model_family="patchcore",
            category="can",
            seed=42,
            config={},
            unexpected="silently accepted",
        )


def test_model_bundle_rejects_unknown_schema_major() -> None:
    with pytest.raises(ValidationError, match="schema major"):
        ModelBundleManifest(
            schema_version="2.0.0",
            category="can",
            runtime_kind="anomalib",
            model_family="patchcore",
            files=[],
        )


def test_real_model_bundle_requires_an_approved_family() -> None:
    with pytest.raises(ValidationError, match="model_family"):
        ModelBundleManifest(
            category="can",
            runtime_kind="anomalib",
            model_family=None,
            files=[],
        )


def test_mock_bundle_requires_synthetic_ci_scope() -> None:
    with pytest.raises(ValidationError, match="synthetic-ci-only"):
        ModelBundleManifest(
            category="can",
            runtime_kind="mock",
            model_family=None,
            evaluation_scope="public-benchmark",
            files=[],
        )


def test_dataset_manifest_hash_changes_when_inventory_changes() -> None:
    base = DatasetManifest(
        archive_url="https://example.test/mvtec_ad_2.tar.gz",
        archive_size=32_739_596_982,
        archive_sha256="a" * 64,
        category_counts={"can": {"train/good": 10}},
    )
    changed = base.model_copy(update={"category_counts": {"can": {"train/good": 11}}})

    assert base.identity != changed.identity


def test_prediction_record_rejects_non_finite_scores() -> None:
    with pytest.raises(ValidationError, match="finite"):
        PredictionRecord(
            input_id="part-001",
            input_sha256="b" * 64,
            category="can",
            anomaly_score=float("nan"),
            anomaly_map_sha256="c" * 64,
            model_bundle_id="bundle-001",
        )


def test_run_record_requires_error_for_failed_run() -> None:
    spec = RunSpec(
        model_family="efficient_ad",
        category="vial",
        seed=17,
        config={},
    )

    with pytest.raises(ValidationError, match="error"):
        RunRecord(spec=spec, status="failed")


def test_sha256_file_streams_exact_file_bytes(tmp_path: Path) -> None:
    payload = (b"mvtec-ad2-contract" * 1024) + b"tail"
    path = tmp_path / "artifact.bin"
    path.write_bytes(payload)

    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()
