from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from inspection_platform.registry.repository import BundleIntegrityError, ModelRegistry


def test_registry_rejects_tampered_weight(tmp_path: Path) -> None:
    weight = tmp_path / "weights.bin"
    weight.write_bytes(b"weights")
    digest = hashlib.sha256(weight.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "category": "can",
                "runtime_kind": "mock",
                "model_family": None,
                "evaluation_scope": "synthetic-ci-only",
                "files": [{"path": "weights.bin", "sha256": digest, "size": 7}],
            }
        ),
        encoding="utf-8",
    )
    weight.write_bytes(b"tampered")
    with pytest.raises(BundleIntegrityError, match="sha256"):
        ModelRegistry(tmp_path).register(manifest)


def test_registry_streams_weight_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    weight = tmp_path / "weights.bin"
    weight.write_bytes(b"weights")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "category": "can",
                "runtime_kind": "mock",
                "model_family": None,
                "evaluation_scope": "synthetic-ci-only",
                "files": [
                    {
                        "path": "weights.bin",
                        "sha256": hashlib.sha256(b"weights").hexdigest(),
                        "size": 7,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def reject_whole_file_read(_path: Path) -> bytes:
        raise AssertionError("registry must stream large artifacts")

    monkeypatch.setattr(Path, "read_bytes", reject_whole_file_read)
    assert ModelRegistry(tmp_path).register(manifest).category == "can"
