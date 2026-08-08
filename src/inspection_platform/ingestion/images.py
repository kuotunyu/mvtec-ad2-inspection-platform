from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

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


def validate_image(stream: BinaryIO, *, filename: str, max_bytes: int) -> ValidatedImage:
    del filename
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
            return ValidatedImage(media_type, image.width, image.height, content)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("image bytes failed decoder verification") from exc


__all__ = ["ImageValidationError", "ValidatedImage", "validate_image"]
