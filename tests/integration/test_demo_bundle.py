from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_demo_bundle import build_demo_bundle, build_public_demo_fixtures


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_demo_bundle_is_byte_stable_and_explicitly_restricted(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifests = build_demo_bundle(first)
    build_demo_bundle(second)
    assert _tree_hash(first) == _tree_hash(second)
    assert all(manifest.runtime_kind == "mock" for manifest in manifests)
    assert all(manifest.model_family is None for manifest in manifests)
    assert all(manifest.evaluation_scope == "synthetic-ci-only" for manifest in manifests)


def test_public_fixture_outcomes_match_the_mock_threshold(tmp_path: Path) -> None:
    build_public_demo_fixtures(tmp_path)
    for image in (tmp_path / "images").glob("*.png"):
        expected = json.loads(
            (tmp_path / "expected" / f"{image.stem}.json").read_text(encoding="utf-8")
        )
        score = int(hashlib.sha256(image.read_bytes()).hexdigest()[:8], 16) / 0xFFFFFFFF
        outcome = "REVIEW" if score >= 0.5 else "PASS"
        assert outcome == expected["intended_mock_outcome"]
