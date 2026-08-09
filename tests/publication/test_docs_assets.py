from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.render_docs_assets import ASSET_NAMES, _manifest_stale, _write_svg_assets


def test_svg_assets_are_written_with_canonical_lf_bytes(tmp_path: Path) -> None:
    _write_svg_assets(tmp_path)

    for name in ("architecture.svg", "workflow.svg"):
        content = (tmp_path / name).read_bytes()
        assert content.endswith(b"\n")
        assert b"\r\n" not in content


def test_manifest_check_is_stable_without_rerendering(tmp_path: Path) -> None:
    hashes: dict[str, str] = {}
    for index, name in enumerate(ASSET_NAMES):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"asset-{index}".encode())
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "assets": hashes,
                "fixture_scope": "synthetic-ci-only",
                "generator": "scripts/render_docs_assets.py",
                "schema_version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )

    assert _manifest_stale(tmp_path) == ()

    (tmp_path / ASSET_NAMES[0]).write_bytes(b"changed")
    assert _manifest_stale(tmp_path) == (ASSET_NAMES[0],)
