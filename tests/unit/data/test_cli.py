from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.data.cli import main, prepare
from experiments.data.manifest import REQUIRED_CATEGORIES, build_dataset_manifest

REQUIRED_IMAGE_PATHS = (
    "train/good/001.png",
    "validation/good/001.png",
    "test_public/good/001.png",
    "test_public/bad/001.png",
    "test_public/ground_truth/bad/001_mask.png",
    "test_private/001.png",
    "test_private_mixed/001.png",
)


def create_valid_dataset(root: Path) -> None:
    for category in REQUIRED_CATEGORIES:
        for relative in REQUIRED_IMAGE_PATHS:
            path = root / category / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"png:{category}:{relative}".encode())


def test_prepare_preserves_existing_dataset_and_writes_external_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "mvtec-ad-2"
    create_valid_dataset(root)
    marker = root / "operator-marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    archive = tmp_path / "mvtec_ad_2.tar.gz"
    archive.write_bytes(b"verified by isolated downloader tests")

    monkeypatch.setattr("experiments.data.cli.download_archive", lambda *_args: archive)

    def fail_if_extract_called(*_args: object) -> None:
        raise AssertionError("an existing dataset must not be overwritten or extracted again")

    monkeypatch.setattr("experiments.data.cli.extract_archive", fail_if_extract_called)

    manifest_path = prepare(root)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_path == root.parent / "mvtec-ad-2.manifest.json"
    assert payload["canonical_sha256"] == build_dataset_manifest(root).identity
    assert str(root.resolve()) not in manifest_path.read_text(encoding="utf-8")
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_prepare_rejects_dataset_root_inside_repository() -> None:
    with pytest.raises(ValueError, match="outside the repository"):
        prepare(Path.cwd() / "runtime-test-dataset")


def test_main_reports_verified_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("experiments.data.cli.prepare", lambda _root: manifest)

    assert main(["prepare", "--root", str(tmp_path / "dataset")]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "manifest": str(manifest),
        "status": "verified",
    }
