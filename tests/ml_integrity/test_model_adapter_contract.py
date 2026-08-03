from __future__ import annotations

from pathlib import Path

import pytest

from experiments.models.base import FitContext, SplitLeakageError, assert_fit_split
from inspection_platform.contracts import DatasetFile, DatasetManifest, sha256_file


def dataset_manifest(root: Path, paths: tuple[Path, ...]) -> DatasetManifest:
    return DatasetManifest(
        archive_url="https://example.com/dataset.tar.gz",
        archive_size=1,
        archive_sha256="a" * 64,
        category_counts={"can": {"train/good": 1, "validation/good": 1}},
        extensions=(".png",),
        files=tuple(
            DatasetFile(
                relative_path=path.relative_to(root).as_posix(),
                size=path.stat().st_size,
                sha256=sha256_file(path),
            )
            for path in paths
        ),
    )


def test_fit_split_uses_manifest_identity_and_allows_only_train_good(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    train_image = root / "can/train/good/001.png"
    validation_image = root / "can/validation/good/001.png"
    train_image.parent.mkdir(parents=True)
    validation_image.parent.mkdir(parents=True)
    train_image.write_bytes(b"train")
    validation_image.write_bytes(b"validation")
    manifest = dataset_manifest(root, (train_image, validation_image))

    valid = FitContext(
        category="can",
        images=(train_image,),
        dataset_root=root,
        dataset_manifest=manifest,
        seed=42,
        output_dir=tmp_path / "run",
        device="cpu",
    )
    assert_fit_split(valid)

    leaked = FitContext(
        category="can",
        images=(validation_image,),
        dataset_root=root,
        dataset_manifest=manifest,
        seed=42,
        output_dir=tmp_path / "run-leaked",
        device="cpu",
    )
    with pytest.raises(SplitLeakageError, match="train/good"):
        assert_fit_split(leaked)


def test_fit_split_rejects_file_not_in_frozen_manifest(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    approved = root / "can/train/good/001.png"
    unapproved = root / "can/train/good/002.png"
    approved.parent.mkdir(parents=True)
    approved.write_bytes(b"approved")
    unapproved.write_bytes(b"unapproved")
    manifest = dataset_manifest(root, (approved,))
    context = FitContext(
        category="can",
        images=(unapproved,),
        dataset_root=root,
        dataset_manifest=manifest,
        seed=42,
        output_dir=tmp_path / "run",
        device="cpu",
    )

    with pytest.raises(SplitLeakageError, match="frozen dataset manifest"):
        assert_fit_split(context)
