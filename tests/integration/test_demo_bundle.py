from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.build_demo_bundle import build_demo_bundle


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
