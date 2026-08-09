from __future__ import annotations

import tarfile
from io import BytesIO

import pytest
from PIL import Image

from inspection_platform.ingestion.archives import ArchiveValidationError, iterate_safe_archive
from inspection_platform.ingestion.images import ImageValidationError, validate_image


def _archive(entries: list[tuple[str, bytes, bytes | None]]) -> BytesIO:
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content, link in entries:
            info = tarfile.TarInfo(name)
            if link is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = link.decode()
            else:
                info.size = len(content)
                archive.addfile(info, BytesIO(content))
                continue
            archive.addfile(info)
    stream.seek(0)
    return stream


@pytest.mark.parametrize(
    "entries",
    [
        [("safe.png", b"x", b"../../escape")],
        [("same.png", b"a", None), ("same.png", b"b", None)],
        [("a.png", b"a" * 8, None), ("b.png", b"b" * 8, None)],
    ],
)
def test_archive_rejects_links_duplicates_and_expansion(
    entries: list[tuple[str, bytes, bytes | None]],
) -> None:
    with pytest.raises(ArchiveValidationError):
        list(iterate_safe_archive(_archive(entries), max_files=10, max_bytes=10))


def test_image_rejects_excessive_dimensions_and_polyglot() -> None:
    image = Image.new("RGB", (20, 20), "white")
    stream = BytesIO()
    image.save(stream, format="PNG")
    with pytest.raises(ImageValidationError):
        validate_image(
            BytesIO(stream.getvalue()), filename="large.png", max_bytes=10_000, max_pixels=100
        )
    with pytest.raises(ImageValidationError):
        validate_image(
            BytesIO(stream.getvalue() + b"<script>alert(1)</script>"),
            filename="polyglot.png",
            max_bytes=10_000,
        )
