from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from scripts.verify_experiments import CleanExportError, verify_clean_export


def test_clean_export_rejects_private_and_absolute_paths(tmp_path: Path) -> None:
    archive = tmp_path / "repo.tar.gz"
    payload = tmp_path / "payload"
    (payload / "predictions").mkdir(parents=True)
    (payload / "predictions" / "private.tiff").write_bytes(b"private")
    (payload / "README.md").write_text("ok\n", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(payload / "README.md", arcname="README.md")
        handle.add(payload / "predictions" / "private.tiff", arcname="predictions/private.tiff")

    with pytest.raises(CleanExportError, match=r"predictions/private\.tiff"):
        verify_clean_export(archive)


def test_clean_export_accepts_declared_source_files(tmp_path: Path) -> None:
    archive = tmp_path / "repo.tar.gz"
    source = tmp_path / "source.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(source, arcname="src/source.py")

    result = verify_clean_export(archive)
    assert result.status == "PASS"
    assert result.file_count == 1
