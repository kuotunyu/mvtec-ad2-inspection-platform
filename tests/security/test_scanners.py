from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.security_scan import scan_root
from scripts.verify_public_boundary import verify_paths


def test_security_scanner_finds_secrets_and_runtime_material(tmp_path: Path) -> None:
    (tmp_path / "safe.py").write_text("print('safe')\n", encoding="utf-8")
    (tmp_path / "model.ckpt").write_bytes(b"weights")
    (tmp_path / "leak.txt").write_text("-----BEGIN " + "PRIVATE KEY-----\n", encoding="utf-8")
    report = scan_root(tmp_path)
    assert not report.ok
    assert {finding.code for finding in report.findings} >= {"secret", "model_artifact"}


def test_public_boundary_allows_only_manifested_synthetic_images(tmp_path: Path) -> None:
    image = tmp_path / "fixtures/public-demo/images/demo.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"synthetic")
    report = verify_paths(tmp_path, [Path("fixtures/public-demo/images/demo.png")])
    assert not report.ok
    assert "unmanifested_image" in report.error_codes


def test_public_boundary_allows_hash_manifested_documentation_images(tmp_path: Path) -> None:
    content = b"synthetic documentation screenshot"
    image = tmp_path / "docs/assets/screenshots/dashboard.webp"
    image.parent.mkdir(parents=True)
    image.write_bytes(content)
    manifest = tmp_path / "docs/assets/manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "screenshots/dashboard.webp": hashlib.sha256(content).hexdigest(),
                }
            }
        ),
        encoding="utf-8",
    )

    report = verify_paths(tmp_path, [image.relative_to(tmp_path), manifest.relative_to(tmp_path)])

    assert report.ok


@pytest.mark.parametrize("corrupt_character", ["\ufffd", "\ue6ed"])
def test_public_boundary_rejects_corrupt_unicode_text(
    tmp_path: Path, corrupt_character: str
) -> None:
    document = tmp_path / "docs/LIMITATIONS.md"
    document.parent.mkdir(parents=True)
    document.write_text(f"public text {corrupt_character}\n", encoding="utf-8")

    report = verify_paths(tmp_path, [document.relative_to(tmp_path)])

    assert not report.ok
    assert "invalid_public_text" in report.error_codes
