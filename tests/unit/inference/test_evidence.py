from __future__ import annotations

import subprocess
import sys
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from inspection_platform.inference.evidence import render_spatial_evidence


def _source() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (8, 6), (40, 80, 120)).save(stream, format="PNG")
    return stream.getvalue()


def test_render_spatial_evidence_produces_distinct_full_size_pngs() -> None:
    anomaly_map = np.arange(12, dtype=np.float32).reshape(3, 4)

    rendered = render_spatial_evidence(_source(), anomaly_map)

    anomaly = Image.open(BytesIO(rendered.anomaly_map_png))
    overlay = Image.open(BytesIO(rendered.overlay_png))
    assert anomaly.format == "PNG"
    assert overlay.format == "PNG"
    assert anomaly.size == (8, 6)
    assert overlay.size == (8, 6)
    assert rendered.anomaly_map_png != rendered.overlay_png
    assert rendered.anomaly_map_sha256 != rendered.overlay_sha256


@pytest.mark.parametrize(
    "anomaly_map",
    [np.ones((2, 2, 2), dtype=np.float32), np.asarray([[float("nan")]], dtype=np.float32)],
)
def test_render_spatial_evidence_rejects_invalid_maps(anomaly_map: np.ndarray) -> None:
    with pytest.raises(ValueError, match="invalid anomaly map"):
        render_spatial_evidence(_source(), anomaly_map)


def test_synthetic_evidence_rendering_does_not_require_ml_extra() -> None:
    code = r"""
import importlib.abc
import sys
from io import BytesIO
from PIL import Image

class BlockNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "numpy" or fullname.startswith("numpy."):
            raise ModuleNotFoundError("numpy intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockNumpy())
from inspection_platform.inference.evidence import render_spatial_evidence
stream = BytesIO()
Image.new("RGB", (4, 4), "white").save(stream, format="PNG")
result = render_spatial_evidence(stream.getvalue(), Image.new("L", (2, 2), 128))
assert result.anomaly_map_png and result.overlay_png
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
