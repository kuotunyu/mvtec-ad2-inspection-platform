from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from experiments.models.base import ArtifactFile, FitArtifact, PredictionArtifact
from inspection_platform.contracts import (
    DatasetFile,
    DatasetManifest,
    PredictionRecord,
    sha256_file,
)

CONFIG_ROOT = Path("experiments/configs/models")


def write_manifest(dataset_root: Path, manifest_path: Path) -> DatasetManifest:
    image_paths = (
        dataset_root / "can/train/good/002.png",
        dataset_root / "can/train/good/001.png",
        dataset_root / "can/validation/good/001.png",
    )
    for path in image_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    manifest = DatasetManifest(
        archive_url="https://example.invalid/mvtec-ad-2.tar.gz",
        archive_size=1,
        archive_sha256="a" * 64,
        category_counts={"can": {"train/good": 2, "validation/good": 1}},
        extensions=(".png",),
        files=tuple(
            DatasetFile(
                relative_path=path.relative_to(dataset_root).as_posix(),
                size=path.stat().st_size,
                sha256=sha256_file(path),
            )
            for path in image_paths
        ),
    )
    payload = manifest.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = manifest.identity
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def test_train_main_builds_manifest_ordered_fit_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from experiments import train

    dataset_root = tmp_path / "dataset"
    manifest_path = tmp_path / "manifest.json"
    manifest = write_manifest(dataset_root, manifest_path)
    output_dir = tmp_path / "fit"
    captured: dict[str, Any] = {}

    class FakeAdapter:
        def fit(self, context: Any) -> FitArtifact:
            captured["context"] = context
            output_dir.mkdir()
            checkpoint = output_dir / "model.ckpt"
            checkpoint.write_bytes(b"checkpoint")
            return FitArtifact(
                family="patchcore",
                category="can",
                checkpoint=ArtifactFile(
                    path=checkpoint,
                    sha256=sha256_file(checkpoint),
                    size=checkpoint.stat().st_size,
                ),
                config_sha256="b" * 64,
                preprocessing_sha256="c" * 64,
                seed=42,
                device="cuda:0",
                environment={"anomalib": "2.5.0"},
            )

    monkeypatch.setattr(train, "create_adapter", lambda *_args: FakeAdapter())

    assert (
        train.main(
            [
                "--config",
                str(CONFIG_ROOT / "patchcore.yaml"),
                "--dataset-root",
                str(dataset_root),
                "--dataset-manifest",
                str(manifest_path),
                "--category",
                "can",
                "--seed",
                "42",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    context = captured["context"]
    assert [path.name for path in context.images] == ["001.png", "002.png"]
    assert context.dataset_manifest.identity == manifest.identity
    artifact_path = output_dir / "fit-artifact.json"
    assert artifact_path.is_file()
    assert json.loads(capsys.readouterr().out) == {
        "artifact": str(artifact_path.resolve()),
        "category": "can",
        "family": "patchcore",
        "status": "trained",
    }


def test_train_rejects_manifest_with_wrong_canonical_identity(
    tmp_path: Path,
) -> None:
    from experiments.train import load_dataset_manifest

    dataset_root = tmp_path / "dataset"
    manifest_path = tmp_path / "manifest.json"
    write_manifest(dataset_root, manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["canonical_sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical identity"):
        load_dataset_manifest(manifest_path)


def test_predict_main_preserves_cli_image_order_and_expected_map_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from experiments import predict

    images = (tmp_path / "second.png", tmp_path / "first.png")
    for image in images:
        image.write_bytes(image.name.encode())
    checkpoint = tmp_path / "model.ckpt"
    checkpoint.write_bytes(b"checkpoint")
    output_dir = tmp_path / "predictions"
    captured: dict[str, Any] = {}

    class FakeAdapter:
        def predict(self, context: Any) -> PredictionArtifact:
            captured["context"] = context
            output_dir.mkdir()
            map_files = []
            records = []
            for index, image in enumerate(context.images):
                map_path = output_dir / f"{index}.npy"
                map_path.write_bytes(b"map")
                digest = sha256_file(map_path)
                map_files.append(
                    ArtifactFile(path=map_path, sha256=digest, size=map_path.stat().st_size)
                )
                records.append(
                    PredictionRecord(
                        input_id=str(index),
                        input_sha256=sha256_file(image),
                        category="can",
                        anomaly_score=float(index),
                        anomaly_map_sha256=digest,
                        model_bundle_id="bundle-1",
                        input_path=image,
                    )
                )
            return PredictionArtifact(
                family="dinomaly",
                category="can",
                split="validation",
                config_sha256="d" * 64,
                records=tuple(records),
                anomaly_maps=tuple(map_files),
            )

    monkeypatch.setattr(predict, "create_adapter", lambda *_args: FakeAdapter())

    assert (
        predict.main(
            [
                "--config",
                str(CONFIG_ROOT / "dinomaly.yaml"),
                "--category",
                "can",
                "--split",
                "validation",
                "--checkpoint",
                str(checkpoint),
                "--model-bundle-id",
                "bundle-1",
                "--output-dir",
                str(output_dir),
                "--images",
                *(str(image) for image in images),
            ]
        )
        == 0
    )

    context = captured["context"]
    assert context.images == tuple(image.resolve() for image in images)
    assert context.expected_map_shapes == ((392, 392), (392, 392))
    artifact_path = output_dir / "prediction-artifact.json"
    assert artifact_path.is_file()
    assert json.loads(capsys.readouterr().out) == {
        "artifact": str(artifact_path.resolve()),
        "category": "can",
        "count": 2,
        "family": "dinomaly",
        "status": "predicted",
    }
