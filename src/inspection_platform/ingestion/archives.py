from __future__ import annotations

import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO


class ArchiveValidationError(ValueError):
    """Raised when an archive contains unsafe or excessive content."""


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    content: bytes


def iterate_safe_archive(
    stream: BinaryIO, *, max_files: int, max_bytes: int
) -> Iterator[ArchiveMember]:
    total = 0
    try:
        with tarfile.open(fileobj=stream, mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > max_files:
                raise ArchiveValidationError("archive contains too many files")
            for member in members:
                name = member.name.replace("\\", "/")
                path = PurePosixPath(name)
                if not member.isfile() or path.is_absolute() or ".." in path.parts:
                    raise ArchiveValidationError(f"unsafe archive member: {name}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ArchiveValidationError(f"cannot read archive member: {name}")
                content = handle.read(max_bytes - total + 1)
                total += len(content)
                if total > max_bytes:
                    raise ArchiveValidationError("archive exceeds uncompressed byte limit")
                yield ArchiveMember(name, content)
    except tarfile.TarError as exc:
        raise ArchiveValidationError("invalid tar archive") from exc


__all__ = ["ArchiveMember", "ArchiveValidationError", "iterate_safe_archive"]
