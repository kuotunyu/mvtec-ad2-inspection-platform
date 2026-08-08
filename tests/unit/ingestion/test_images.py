from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from inspection_platform.ingestion.images import ImageValidationError, validate_image


def _png() -> BytesIO:
    image = Image.new("RGB", (4, 4), "red")
    stream = BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream


def test_validate_image_decodes_png() -> None:
    result = validate_image(_png(), filename="sample.png", max_bytes=1024 * 1024)
    assert result.media_type == "image/png"
    assert result.width == 4 and result.height == 4


def test_validate_image_rejects_mislabeled_bytes() -> None:
    with pytest.raises(ImageValidationError):
        validate_image(BytesIO(b"not-an-image"), filename="sample.png", max_bytes=1024)
