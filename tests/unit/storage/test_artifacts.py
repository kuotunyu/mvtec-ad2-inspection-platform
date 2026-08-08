from __future__ import annotations

from io import BytesIO
from pathlib import Path

from inspection_platform.storage.artifacts import ArtifactStore


def test_artifact_store_is_content_addressed_and_atomic(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    first = store.put_stream(BytesIO(b"hello"), media_type="text/plain")
    second = store.put_stream(BytesIO(b"hello"), media_type="text/plain")
    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert first.path.read_bytes() == b"hello"
