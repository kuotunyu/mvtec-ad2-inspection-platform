from __future__ import annotations

from pathlib import Path

from experiments.data.download import MVTECAD2_SOURCE
from inspection_platform.contracts import DatasetFile, DatasetManifest, sha256_file

REQUIRED_CATEGORIES = (
    "can",
    "fabric",
    "fruit_jelly",
    "rice",
    "sheet_metal",
    "vial",
    "wallplugs",
    "walnuts",
)
REQUIRED_SPLITS = (
    "test_private",
    "test_private_mixed",
    "test_public/bad",
    "test_public/good",
    "test_public/ground_truth/bad",
    "train/good",
    "validation/good",
)


class DatasetLayoutError(RuntimeError):
    """Raised when a dataset tree violates the frozen split contract."""


def _png_files(directory: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() == ".png"
            ),
            key=lambda path: path.name,
        )
    )


def _verify_public_masks(category_root: Path) -> None:
    anomalies = _png_files(category_root / "test_public" / "bad")
    masks = _png_files(category_root / "test_public" / "ground_truth" / "bad")
    expected = {f"{image.stem}_mask{image.suffix.lower()}" for image in anomalies}
    actual = {mask.name.lower() for mask in masks}
    missing = expected - actual
    if missing:
        raise DatasetLayoutError(f"Missing mask(s) for public anomalies: {sorted(missing)}")
    orphaned = actual - expected
    if orphaned:
        raise DatasetLayoutError(f"Orphan public mask(s): {sorted(orphaned)}")


def build_dataset_manifest(root: Path) -> DatasetManifest:
    """Validate official splits and hash every dataset PNG by relative path."""

    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise DatasetLayoutError(f"dataset root is not a directory: {root}")

    category_counts: dict[str, dict[str, int]] = {}
    approved_files: set[Path] = set()
    for category in REQUIRED_CATEGORIES:
        category_root = root / category
        if not category_root.is_dir():
            raise DatasetLayoutError(f"missing category directory: {category}")

        split_counts: dict[str, int] = {}
        for split in REQUIRED_SPLITS:
            directory = category_root.joinpath(*split.split("/"))
            if not directory.is_dir():
                raise DatasetLayoutError(f"missing required split: {category}/{split}")
            files = _png_files(directory)
            if not files and split != "test_public/ground_truth/bad":
                raise DatasetLayoutError(
                    f"required split contains no PNG files: {category}/{split}"
                )
            split_counts[split] = len(files)
            approved_files.update(path.resolve() for path in files)

        _verify_public_masks(category_root)
        category_counts[category] = split_counts

    all_png_files = {
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".png"
    }
    unapproved = all_png_files - approved_files
    if unapproved:
        relative = sorted(path.relative_to(root).as_posix() for path in unapproved)
        raise DatasetLayoutError(f"PNG file(s) outside approved split directories: {relative}")

    file_records = tuple(
        DatasetFile(
            relative_path=path.relative_to(root).as_posix(),
            size=path.stat().st_size,
            sha256=sha256_file(path),
        )
        for path in sorted(approved_files, key=lambda item: item.relative_to(root).as_posix())
    )
    extensions = tuple(sorted({path.suffix.lower() for path in approved_files}))
    return DatasetManifest(
        archive_url=MVTECAD2_SOURCE.url,
        archive_size=MVTECAD2_SOURCE.expected_size,
        archive_sha256=MVTECAD2_SOURCE.sha256,
        category_counts=category_counts,
        extensions=extensions,
        files=file_records,
    )
