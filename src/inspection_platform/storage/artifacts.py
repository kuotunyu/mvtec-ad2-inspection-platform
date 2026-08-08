from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO


@dataclass(frozen=True)
class ArtifactRef:
    sha256: str
    media_type: str
    path: Path


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_stream(self, stream: BinaryIO, *, media_type: str) -> ArtifactRef:
        digest = sha256()
        with NamedTemporaryFile(dir=self.root, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                temporary.write(chunk)
        value = digest.hexdigest()
        destination = self.root / value[:2] / value
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary_path.replace(destination)
        else:
            temporary_path.unlink()
        return ArtifactRef(value, media_type, destination)


__all__ = ["ArtifactRef", "ArtifactStore"]
