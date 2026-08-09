from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import BinaryIO
from unicodedata import normalize
from urllib.parse import unquote

from PIL import Image, UnidentifiedImageError


class ImageValidationError(ValueError):
    """Raised when uploaded bytes are not a permitted decoded image."""


@dataclass(frozen=True)
class ValidatedImage:
    media_type: str
    width: int
    height: int
    content: bytes


_MEDIA_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def sanitize_filename(filename: str) -> str:
    normalized = normalize("NFKC", unquote(filename)).replace("\\", "/")
    basename = PurePosixPath(normalized).name
    cleaned = "".join(
        character for character in basename if character >= " " and character != "\x7f"
    )
    if cleaned in {"", ".", ".."}:
        return "image"
    return cleaned[-255:]


def _has_exact_container_boundary(content: bytes, image_format: str) -> bool:
    if image_format == "PNG":
        return content.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    if image_format == "JPEG":
        return content.endswith(b"\xff\xd9")
    if image_format == "WEBP":
        return (
            len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
            and int.from_bytes(content[4:8], "little") + 8 == len(content)
        )
    return False


def validate_image(
    stream: BinaryIO, *, filename: str, max_bytes: int, max_pixels: int = 100_000_000
) -> ValidatedImage:
    sanitize_filename(filename)
    content = stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ImageValidationError("image exceeds configured byte limit")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            media_type = _MEDIA_TYPES.get(image.format or "")
            if media_type is None:
                raise ImageValidationError("unsupported image format")
            if image.width * image.height > max_pixels:
                raise ImageValidationError("image exceeds configured pixel limit")
            if not _has_exact_container_boundary(content, image.format or ""):
                raise ImageValidationError("image contains trailing or invalid container data")
            return ValidatedImage(media_type, image.width, image.height, content)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("image bytes failed decoder verification") from exc


__all__ = ["ImageValidationError", "ValidatedImage", "sanitize_filename", "validate_image"]
