from __future__ import annotations

from bisect import bisect
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import label  # type: ignore[import-untyped]
from sklearn.metrics import average_precision_score, roc_auc_score  # type: ignore[import-untyped]

from experiments.metrics.artifacts import PixelMetrics

NDArrayBool = NDArray[np.bool_]
NDArrayFloat = NDArray[np.float64]
PRO_FPR_LIMIT = 0.30


def _validate_pixel_inputs(
    masks: NDArrayBool,
    maps: NDArrayFloat,
    mask_ids: Sequence[str] | None,
    map_ids: Sequence[str] | None,
) -> tuple[NDArray[np.bool_], NDArray[np.float64]]:
    checked_masks = np.asarray(masks)
    checked_maps = np.asarray(maps, dtype=np.float64)
    if checked_masks.ndim != 3 or checked_maps.ndim != 3:
        raise ValueError("masks and maps must be three-dimensional (image, height, width)")
    if checked_masks.shape != checked_maps.shape:
        raise ValueError("masks and maps must have the same shape")
    if checked_masks.size == 0:
        raise ValueError("masks and maps must not be empty")
    if checked_masks.dtype != np.bool_:
        raise ValueError("masks must use boolean dtype")
    if not np.isfinite(checked_maps).all():
        raise ValueError("maps must contain only finite values")
    if (mask_ids is None) != (map_ids is None):
        raise ValueError("mask and map image order metadata must be provided together")
    if mask_ids is not None and map_ids is not None:
        if len(mask_ids) != checked_masks.shape[0] or len(map_ids) != checked_maps.shape[0]:
            raise ValueError("image order metadata must match the image count")
        if tuple(mask_ids) != tuple(map_ids):
            raise ValueError("mask and map image order differs")
    return checked_masks, checked_maps


def _compute_pro_curve(
    masks: NDArray[np.bool_], maps: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], int, int]:
    structure = np.ones((3, 3), dtype=np.int8)
    fp_changes = np.zeros(masks.shape, dtype=np.uint64)
    pro_changes = np.zeros(masks.shape, dtype=np.float64)
    normal_pixel_count = 0
    region_count = 0

    for image_index, mask in enumerate(masks):
        labeled, components = label(mask, structure)
        region_count += int(components)
        normal_mask = labeled == 0
        normal_pixel_count += int(np.count_nonzero(normal_mask))
        fp_changes[image_index, normal_mask] = 1
        for component in range(1, components + 1):
            region_mask = labeled == component
            pro_changes[image_index, region_mask] = 1.0 / np.count_nonzero(region_mask)

    if normal_pixel_count == 0 or region_count == 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty, normal_pixel_count, region_count

    scores = maps.ravel().copy()
    order = np.argsort(scores)[::-1]
    scores = scores[order]
    sorted_fp = fp_changes.ravel()[order]
    sorted_pro = pro_changes.ravel()[order]

    cumulative_fp = np.cumsum(sorted_fp, dtype=np.uint64).astype(np.float32)
    fprs = cumulative_fp / normal_pixel_count
    pros = np.cumsum(sorted_pro, dtype=np.float64) / region_count
    keep = np.append(np.diff(scores) != 0, np.True_)
    fprs = np.clip(fprs[keep], a_min=None, a_max=1.0).astype(np.float64)
    pros = np.clip(pros[keep], a_min=None, a_max=1.0)
    zero = np.array([0.0])
    one = np.array([1.0])
    return (
        np.concatenate((zero, fprs, one)),
        np.concatenate((zero, pros, one)),
        normal_pixel_count,
        region_count,
    )


def _trapezoid_to_limit(x: NDArray[np.float64], y: NDArray[np.float64], x_max: float) -> float:
    correction = 0.0
    if x_max not in x:
        insertion = bisect(x, x_max)
        if not 0 < insertion < len(x):
            raise ValueError("integration limit must lie within the curve")
        interpolated = y[insertion - 1] + (
            (y[insertion] - y[insertion - 1])
            * (x_max - x[insertion - 1])
            / (x[insertion] - x[insertion - 1])
        )
        correction = float(0.5 * (interpolated + y[insertion - 1]) * (x_max - x[insertion - 1]))
    within_limit = x <= x_max
    limited_x = x[within_limit]
    limited_y = y[within_limit]
    area = np.sum(0.5 * (limited_y[1:] + limited_y[:-1]) * (limited_x[1:] - limited_x[:-1]))
    return float(area + correction)


def compute_pixel_metrics(
    masks: NDArrayBool,
    maps: NDArrayFloat,
    *,
    mask_ids: Sequence[str] | None = None,
    map_ids: Sequence[str] | None = None,
) -> PixelMetrics:
    """Compute pixel AUROC/AUPR and official-compatible AU-PRO through FPR 0.30."""

    checked_masks, checked_maps = _validate_pixel_inputs(masks, maps, mask_ids, map_ids)
    anomaly_pixel_count = int(np.count_nonzero(checked_masks))
    normal_pixel_count = checked_masks.size - anomaly_pixel_count
    fprs, pros, pro_normal_count, region_count = _compute_pro_curve(checked_masks, checked_maps)
    if normal_pixel_count != pro_normal_count:
        raise AssertionError("pixel and PRO normal counts diverged")

    has_both_classes = normal_pixel_count > 0 and anomaly_pixel_count > 0
    auroc = None
    average_precision = None
    if has_both_classes:
        flat_masks = checked_masks.ravel()
        flat_maps = checked_maps.ravel()
        auroc = float(roc_auc_score(flat_masks, flat_maps))
        average_precision = float(average_precision_score(flat_masks, flat_maps))

    au_pro = None
    if len(fprs) > 0:
        au_pro = _trapezoid_to_limit(fprs, pros, PRO_FPR_LIMIT) / PRO_FPR_LIMIT

    return PixelMetrics(
        auroc=auroc,
        average_precision=average_precision,
        au_pro=au_pro,
        normal_pixel_count=normal_pixel_count,
        anomaly_pixel_count=anomaly_pixel_count,
        region_count=region_count,
    )
