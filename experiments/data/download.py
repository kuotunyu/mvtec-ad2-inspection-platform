from __future__ import annotations

import http.client
import os
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import truststore

from inspection_platform.contracts import sha256_file

_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class DownloadError(RuntimeError):
    """Raised when the archive cannot be downloaded reliably."""


class IntegrityError(DownloadError):
    """Raised when downloaded bytes do not match their frozen identity."""


@dataclass(frozen=True, slots=True)
class DatasetSource:
    name: str
    url: str
    expected_size: int
    sha256: str

    def __post_init__(self) -> None:
        if self.expected_size <= 0:
            raise ValueError("expected_size must be positive")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("sha256 must be a lowercase hexadecimal SHA-256 digest")


MVTECAD2_SOURCE = DatasetSource(
    name="mvtec_ad_2",
    url=(
        "https://www.mydrive.ch/shares/150997/701c90d3aea6588f404936e32a674602/"
        "download/466712769-1743429042/mvtec_ad_2.tar.gz"
    ),
    expected_size=32_739_596_982,
    sha256="c0ded99ef32bfc8e352d52beb44515e5b292b8598cb963aadfa91ca0763505e4",
)


def create_tls_context() -> ssl.SSLContext:
    """Create a verifying TLS context backed by the native operating-system store."""

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _verify_archive(path: Path, source: DatasetSource) -> None:
    actual_size = path.stat().st_size
    if actual_size != source.expected_size:
        raise IntegrityError(
            f"archive byte count mismatch: expected {source.expected_size}, got {actual_size}"
        )
    actual_hash = sha256_file(path)
    if actual_hash != source.sha256:
        raise IntegrityError(
            f"archive SHA-256 mismatch: expected {source.sha256}, got {actual_hash}"
        )


def _download_once(source: DatasetSource, partial: Path, tls_context: ssl.SSLContext) -> None:
    offset = partial.stat().st_size if partial.exists() else 0
    request = Request(source.url, headers={"User-Agent": "mvtec-ad2-inspection-platform/0.1"})
    if offset:
        request.add_header("Range", f"bytes={offset}-")

    with urlopen(request, timeout=60, context=tls_context) as response:
        status = response.status
        mode = "ab"
        if offset and status == 200:
            mode = "wb"
        elif status == 206:
            content_range = response.headers.get("Content-Range", "")
            if not content_range.startswith(f"bytes {offset}-"):
                raise DownloadError(f"invalid Content-Range for resume: {content_range!r}")
        elif status != 200:
            raise DownloadError(f"unexpected HTTP status {status}")

        with partial.open(mode) as stream:
            while chunk := response.read(_DOWNLOAD_CHUNK_SIZE):
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())


def download_archive(
    source: DatasetSource,
    destination: Path,
    *,
    max_attempts: int = 3,
) -> Path:
    """Resume, verify, and atomically finalize one dataset archive."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")

    tls_context = create_tls_context()
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(f"{destination}.part")

    if destination.exists():
        try:
            _verify_archive(destination, source)
        except IntegrityError:
            destination.unlink()
            raise
        return destination

    if partial.exists() and partial.stat().st_size > source.expected_size:
        actual_size = partial.stat().st_size
        partial.unlink()
        raise IntegrityError(
            "partial archive byte count exceeds expected size: "
            f"{actual_size} > {source.expected_size}"
        )

    if partial.exists() and partial.stat().st_size == source.expected_size:
        try:
            _verify_archive(partial, source)
        except IntegrityError:
            partial.unlink()
            raise
        os.replace(partial, destination)
        return destination

    retryable_errors = (URLError, TimeoutError, OSError, http.client.IncompleteRead)
    for attempt in range(1, max_attempts + 1):
        try:
            _download_once(source, partial, tls_context)
            actual_size = partial.stat().st_size
            if actual_size < source.expected_size:
                if attempt == max_attempts:
                    raise DownloadError(
                        f"download incomplete after {max_attempts} attempt(s): "
                        f"expected {source.expected_size} bytes, got {actual_size}"
                    )
                continue
            _verify_archive(partial, source)
            os.replace(partial, destination)
            return destination
        except IntegrityError:
            if partial.exists():
                partial.unlink()
            raise
        except retryable_errors as error:
            if attempt == max_attempts:
                raise DownloadError(
                    f"download failed after {max_attempts} attempt(s): {type(error).__name__}"
                ) from error

    raise AssertionError("download attempt loop terminated unexpectedly")
