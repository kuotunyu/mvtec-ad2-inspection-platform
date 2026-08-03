from __future__ import annotations

import importlib.util
import math
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from inspection_platform.contracts import sha256_file

OFFICIAL_EVALUATION_ARCHIVE_URL = (
    "https://www.mydrive.ch/shares/150450/bb24b914a28ddd2b5e35bd53d23177cd/"
    "download/439517473-1665675012/mvtec_ad_evaluation.tar.xz"
)
OFFICIAL_EVALUATION_ARCHIVE_SHA256 = (
    "dfcda7d67eee25316ec6ae5042c0b1684a4cabf33b2346be351e2ce36013f220"
)
OFFICIAL_PRO_CURVE_SHA256 = "80feff3b5c96023a93ec3a28494583c7732f639547f572982952bb6d0469a29d"
OFFICIAL_GENERIC_UTIL_SHA256 = "96ed3135f23f49a75a767891dd1e3c975973590af31cad0cc39f655f6d76fef2"

NDArrayBool = NDArray[np.bool_]
NDArrayFloat = NDArray[np.float64]


class OfficialUtilityError(RuntimeError):
    """Raised when the external reviewed utility does not match its frozen identity."""


def _load_verified_module(name: str, path: Path, expected_sha256: str) -> ModuleType:
    path = path.resolve(strict=True)
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise OfficialUtilityError(
            f"official utility SHA-256 mismatch for {path.name}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise OfficialUtilityError(f"could not load official utility: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def official_au_pro(
    root: Path,
    masks: NDArrayBool,
    maps: NDArrayFloat,
    *,
    fpr_limit: float,
) -> float:
    """Invoke only the hash-pinned official PRO and trapezoid functions."""

    if not math.isfinite(fpr_limit) or not 0.0 < fpr_limit <= 1.0:
        raise ValueError("fpr_limit must be finite and in (0, 1]")
    root = root.expanduser().resolve(strict=True)
    pro_module = _load_verified_module(
        "mvtec_official_pro_curve_util",
        root / "pro_curve_util.py",
        OFFICIAL_PRO_CURVE_SHA256,
    )
    generic_module = _load_verified_module(
        "mvtec_official_generic_util",
        root / "generic_util.py",
        OFFICIAL_GENERIC_UTIL_SHA256,
    )
    compute_pro = cast(
        Callable[..., tuple[NDArray[np.float64], NDArray[np.float64]]],
        pro_module.compute_pro,
    )
    trapezoid = cast(Callable[..., Any], generic_module.trapezoid)
    fprs, pros = compute_pro(
        anomaly_maps=[np.asarray(item) for item in maps],
        ground_truth_maps=[np.asarray(item) for item in masks],
    )
    area = float(trapezoid(fprs, pros, x_max=fpr_limit))
    return area / fpr_limit
