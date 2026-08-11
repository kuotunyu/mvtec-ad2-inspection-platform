from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any, cast

from PIL import Image


@dataclass(frozen=True)
class SpatialEvidence:
    anomaly_map_png: bytes
    overlay_png: bytes
    anomaly_map_sha256: str
    overlay_sha256: str


def render_spatial_evidence(image_bytes: bytes, anomaly_map: object) -> SpatialEvidence:
    """Render a normalized map and red evidence overlay at the source resolution."""
    if isinstance(anomaly_map, Image.Image):
        grayscale = anomaly_map.convert("L")
    else:
        import numpy as np

        values = np.asarray(anomaly_map, dtype=np.float32)
        if values.ndim != 2 or values.size == 0 or not np.isfinite(values).all():
            raise ValueError("invalid anomaly map")
        low, high = float(values.min()), float(values.max())
        normalized = np.zeros_like(values) if high <= low else (values - low) / (high - low)
        grayscale = Image.fromarray(
            cast(Any, np.uint8(np.clip(normalized * 255, 0, 255))), mode="L"
        )
    with Image.open(BytesIO(image_bytes)) as decoded:
        source = decoded.convert("RGB")
    resized = grayscale.resize(source.size, Image.Resampling.BILINEAR)
    red = Image.new("RGB", source.size, (235, 55, 55))
    overlay = Image.composite(red, source, resized.point(lambda value: int(value * 0.55)))
    map_stream, overlay_stream = BytesIO(), BytesIO()
    resized.save(map_stream, format="PNG", optimize=False)
    overlay.save(overlay_stream, format="PNG", optimize=False)
    map_bytes, overlay_bytes = map_stream.getvalue(), overlay_stream.getvalue()
    return SpatialEvidence(
        anomaly_map_png=map_bytes,
        overlay_png=overlay_bytes,
        anomaly_map_sha256=hashlib.sha256(map_bytes).hexdigest(),
        overlay_sha256=hashlib.sha256(overlay_bytes).hexdigest(),
    )


__all__ = ["SpatialEvidence", "render_spatial_evidence"]
