from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(model: BaseModel) -> str:
    """Hash a model's canonical JSON representation, excluding computed fields."""

    payload = model.model_dump(mode="json", exclude_computed_fields=True)
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
