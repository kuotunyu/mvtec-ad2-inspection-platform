from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts import render_docs_assets
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


def test_demo_animation_preserves_workflow_order_and_plays_once(tmp_path: Path) -> None:
    frame_names = (
        "new-inspection",
        "dashboard",
        "job-evidence",
        "review",
        "model-evidence",
    )
    colors = (
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 0, 255),
    )
    screenshot_root = tmp_path / "screenshots"
    screenshot_root.mkdir()
    for name, color in zip(frame_names, colors, strict=True):
        Image.new("RGB", (60, 40), color).save(screenshot_root / f"{name}.webp", lossless=True)

    writer = getattr(render_docs_assets, "_write_demo_animation", None)
    assert callable(writer), "documentation asset generator must expose the demo writer"

    writer(tmp_path)

    output = tmp_path / "demo-workflow.gif"
    with Image.open(output) as animation:
        assert animation.format == "GIF"
        assert animation.size == (960, 640)
        assert animation.n_frames == len(colors)
        assert "loop" not in animation.info
        actual_colors: list[tuple[int, int, int]] = []
        durations: list[int] = []
        for index in range(animation.n_frames):
            animation.seek(index)
            actual_colors.append(animation.convert("RGB").getpixel((0, 0)))
            durations.append(animation.info["duration"])
    assert actual_colors == list(colors)
    assert durations == [900] * len(colors)


def test_demo_animation_fails_closed_when_a_workflow_frame_is_missing(tmp_path: Path) -> None:
    screenshot_root = tmp_path / "screenshots"
    screenshot_root.mkdir()
    Image.new("RGB", (60, 40), (255, 0, 0)).save(
        screenshot_root / "new-inspection.webp", lossless=True
    )
    writer = getattr(render_docs_assets, "_write_demo_animation", None)
    assert callable(writer), "documentation asset generator must expose the demo writer"

    with pytest.raises(FileNotFoundError):
        writer(tmp_path)

    assert not (tmp_path / "demo-workflow.gif").exists()
