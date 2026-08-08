from __future__ import annotations

import tarfile
from io import BytesIO

import pytest

from inspection_platform.ingestion.archives import ArchiveValidationError, iterate_safe_archive


@pytest.mark.parametrize("name", ["../x.png", "/tmp/x.png", "a/../../x.png"])
def test_archive_rejects_path_escape(name: str) -> None:
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = 1
        archive.addfile(info, BytesIO(b"x"))
    stream.seek(0)
    with pytest.raises(ArchiveValidationError):
        list(iterate_safe_archive(stream, max_files=10, max_bytes=100))
