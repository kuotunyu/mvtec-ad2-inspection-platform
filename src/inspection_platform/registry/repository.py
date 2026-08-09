from __future__ import annotations

import json
from pathlib import Path

from inspection_platform.contracts import sha256_file
from inspection_platform.contracts.models import ModelBundleManifest


class BundleIntegrityError(ValueError):
    """Raised when a model bundle fails manifest or file verification."""


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def register(self, manifest_path: Path) -> ModelBundleManifest:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        try:
            manifest = ModelBundleManifest.model_validate(payload)
        except Exception as exc:
            raise BundleIntegrityError("invalid model manifest") from exc
        for bundle_file in manifest.files:
            path = self.root / bundle_file.path
            if not path.is_file():
                raise BundleIntegrityError(f"missing bundle file: {bundle_file.path}")
            actual = sha256_file(path)
            if actual != bundle_file.sha256:
                raise BundleIntegrityError(f"sha256 mismatch: {bundle_file.path}")
            if path.stat().st_size != bundle_file.size:
                raise BundleIntegrityError(f"size mismatch: {bundle_file.path}")
        return manifest


__all__ = ["BundleIntegrityError", "ModelRegistry"]
