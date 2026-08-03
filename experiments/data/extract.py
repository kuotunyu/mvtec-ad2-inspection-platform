from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import IO


class ExtractionError(RuntimeError):
    """Raised when archive extraction cannot complete atomically."""


class UnsafeArchiveError(ExtractionError):
    """Raised when an archive member could escape or alter the filesystem."""


class DestinationExistsError(ExtractionError):
    """Raised rather than replacing an existing dataset tree."""


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    has_unsafe_windows_part = any(
        ":" in part or part != part.rstrip(" .") or PureWindowsPath(part).is_reserved()
        for part in path.parts
    )
    if (
        not normalized
        or "\x00" in normalized
        or path.is_absolute()
        or ".." in path.parts
        or has_unsafe_windows_part
    ):
        raise UnsafeArchiveError(f"unsafe archive path: {name!r}")
    return path


def _write_member(stream: IO[bytes], target: Path, expected_size: int) -> None:
    written = 0
    with target.open("xb") as output:
        while chunk := stream.read(1024 * 1024):
            output.write(chunk)
            written += len(chunk)
        output.flush()
        os.fsync(output.fileno())
    if written != expected_size:
        raise ExtractionError(
            f"archive member size mismatch for {target.name!r}: "
            f"expected {expected_size}, got {written}"
        )


def extract_archive(archive: Path, destination: Path) -> Path:
    """Extract regular files into a temporary sibling, then rename atomically."""

    archive = archive.expanduser().resolve(strict=True)
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise DestinationExistsError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.extract-", dir=destination.parent)
    ).resolve()
    seen: set[PurePosixPath] = set()
    try:
        with tarfile.open(archive, mode="r|*") as tar:
            for member in tar:
                relative = _safe_member_path(member.name)
                if relative in seen:
                    raise UnsafeArchiveError(f"duplicate archive member: {member.name!r}")
                seen.add(relative)

                target = temporary.joinpath(*relative.parts).resolve()
                if os.path.commonpath((temporary, target)) != str(temporary):
                    raise UnsafeArchiveError(f"unsafe archive path: {member.name!r}")

                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isreg():
                    raise UnsafeArchiveError(f"unsupported archive member type for {member.name!r}")

                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is None:
                    raise ExtractionError(f"could not read archive member: {member.name!r}")
                with extracted:
                    _write_member(extracted, target, member.size)

        staged_root = temporary
        top_level_entries = tuple(temporary.iterdir())
        official_wrapper = temporary / "mvtec_ad_2"
        if top_level_entries == (official_wrapper,) and official_wrapper.is_dir():
            staged_root = official_wrapper

        os.replace(staged_root, destination)
        if temporary.exists():
            temporary.rmdir()
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return destination
