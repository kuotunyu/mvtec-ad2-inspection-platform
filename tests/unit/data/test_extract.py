from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from experiments.data.extract import DestinationExistsError, UnsafeArchiveError, extract_archive


def build_tar(tmp_path: Path, members: list[tuple[str, bytes]]) -> Path:
    archive = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for name, payload in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            stream.addfile(info, io.BytesIO(payload))
    return archive


@pytest.mark.parametrize(
    "member",
    [
        "../escape",
        "/absolute",
        "ok/../../escape",
        "C:/escape",
        "..\\escape",
        "CON",
        "can/train/good/image.png:stream",
    ],
)
def test_extract_rejects_path_escape(member: str, tmp_path: Path) -> None:
    archive = build_tar(tmp_path, [(member, b"unsafe")])
    destination = tmp_path / "out"

    with pytest.raises(UnsafeArchiveError, match="unsafe archive path"):
        extract_archive(archive, destination)

    assert not destination.exists()
    assert list(tmp_path.glob(".out.extract-*")) == []


@pytest.mark.parametrize("entry_type", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_extract_rejects_links_and_special_files(entry_type: bytes, tmp_path: Path) -> None:
    archive = tmp_path / "special.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo(name="unsafe-entry")
        info.type = entry_type
        info.linkname = "target"
        stream.addfile(info)

    with pytest.raises(UnsafeArchiveError, match="unsupported archive member"):
        extract_archive(archive, tmp_path / "out")


def test_extract_writes_verified_tree_atomically(tmp_path: Path) -> None:
    archive = build_tar(
        tmp_path,
        [("can/train/good/001.png", b"png-one"), ("can/validation/good/002.png", b"png-two")],
    )
    destination = tmp_path / "out"

    result = extract_archive(archive, destination)

    assert result == destination.resolve()
    assert (destination / "can/train/good/001.png").read_bytes() == b"png-one"
    assert (destination / "can/validation/good/002.png").read_bytes() == b"png-two"
    assert list(tmp_path.glob(".out.extract-*")) == []


def test_extract_strips_only_the_official_archive_wrapper(tmp_path: Path) -> None:
    archive = build_tar(
        tmp_path,
        [("mvtec_ad_2/can/train/good/001.png", b"png-one")],
    )
    destination = tmp_path / "out"

    extract_archive(archive, destination)

    assert (destination / "can/train/good/001.png").read_bytes() == b"png-one"
    assert not (destination / "mvtec_ad_2").exists()


def test_extract_preserves_existing_destination(tmp_path: Path) -> None:
    archive = build_tar(tmp_path, [("new.txt", b"new")])
    destination = tmp_path / "out"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(DestinationExistsError):
        extract_archive(archive, destination)

    assert marker.read_text(encoding="utf-8") == "keep"
