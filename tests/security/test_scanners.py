from __future__ import annotations

from pathlib import Path

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
