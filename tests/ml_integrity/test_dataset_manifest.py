from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from experiments.data.manifest import (
    REQUIRED_CATEGORIES,
    DatasetLayoutError,
    build_dataset_manifest,
)

REQUIRED_IMAGE_PATHS = (
    "train/good/001.png",
    "validation/good/001.png",
    "test_public/good/001.png",
    "test_public/bad/001.png",
    "test_public/ground_truth/bad/001_mask.png",
    "test_private/001.png",
    "test_private_mixed/001.png",
)


@pytest.fixture
def valid_dataset_tree(tmp_path: Path) -> Path:
    root = tmp_path / "mvtec-ad-2"
    for category in REQUIRED_CATEGORIES:
        for relative in REQUIRED_IMAGE_PATHS:
            path = root / category / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"png:{category}:{relative}".encode())
    return root


def test_manifest_inventories_all_categories_and_files(valid_dataset_tree: Path) -> None:
    manifest = build_dataset_manifest(valid_dataset_tree)

    assert tuple(manifest.category_counts) == REQUIRED_CATEGORIES
    assert manifest.category_counts["can"] == {
        "test_private": 1,
        "test_private_mixed": 1,
        "test_public/bad": 1,
        "test_public/good": 1,
        "test_public/ground_truth/bad": 1,
        "train/good": 1,
        "validation/good": 1,
    }
    assert len(manifest.files) == len(REQUIRED_CATEGORIES) * len(REQUIRED_IMAGE_PATHS)
    assert [item.relative_path for item in manifest.files] == sorted(
        item.relative_path for item in manifest.files
    )
    assert manifest.extensions == (".png",)


def test_manifest_identity_does_not_depend_on_dataset_location(
    valid_dataset_tree: Path, tmp_path: Path
) -> None:
    copied = tmp_path / "copied-dataset"
    shutil.copytree(valid_dataset_tree, copied)

    assert (
        build_dataset_manifest(valid_dataset_tree).identity
        == build_dataset_manifest(copied).identity
    )


def test_manifest_requires_all_official_splits(valid_dataset_tree: Path) -> None:
    shutil.rmtree(valid_dataset_tree / "can" / "test_private_mixed")

    with pytest.raises(DatasetLayoutError, match="test_private_mixed"):
        build_dataset_manifest(valid_dataset_tree)


def test_manifest_requires_matching_public_mask(valid_dataset_tree: Path) -> None:
    (valid_dataset_tree / "can/test_public/ground_truth/bad/001_mask.png").unlink()

    with pytest.raises(DatasetLayoutError, match="Missing mask"):
        build_dataset_manifest(valid_dataset_tree)


def test_manifest_rejects_images_outside_approved_splits(valid_dataset_tree: Path) -> None:
    leaked = valid_dataset_tree / "can/train/bad/leaked.png"
    leaked.parent.mkdir(parents=True)
    leaked.write_bytes(b"not allowed")

    with pytest.raises(DatasetLayoutError, match="outside approved split"):
        build_dataset_manifest(valid_dataset_tree)
