from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import average_precision_score, roc_auc_score  # type: ignore[import-untyped]

from experiments.metrics.artifacts import ImageMetrics

NDArrayInt = NDArray[np.int64]
NDArrayFloat = NDArray[np.float64]


def compute_image_metrics(labels: NDArrayInt, scores: NDArrayFloat) -> ImageMetrics:
    """Compute frozen image AUROC/AUPR without inventing single-class values."""

    checked_labels = np.asarray(labels)
    checked_scores = np.asarray(scores, dtype=np.float64)
    if checked_labels.ndim != 1 or checked_scores.ndim != 1:
        raise ValueError("labels and scores must be one-dimensional")
    if checked_labels.size == 0:
        raise ValueError("labels and scores must not be empty")
    if len(checked_labels) != len(checked_scores):
        raise ValueError("labels and scores must have the same length")
    if not np.issubdtype(checked_labels.dtype, np.integer) and checked_labels.dtype != np.bool_:
        raise ValueError("labels must be binary integers")
    if not np.isin(checked_labels, (0, 1)).all():
        raise ValueError("labels must be binary")
    if not np.isfinite(checked_scores).all():
        raise ValueError("scores must contain only finite values")

    anomaly_count = int(np.count_nonzero(checked_labels))
    normal_count = len(checked_labels) - anomaly_count
    if normal_count == 0 or anomaly_count == 0:
        return ImageMetrics(
            auroc=None,
            average_precision=None,
            normal_count=normal_count,
            anomaly_count=anomaly_count,
        )

    return ImageMetrics(
        auroc=float(roc_auc_score(checked_labels, checked_scores)),
        average_precision=float(average_precision_score(checked_labels, checked_scores)),
        normal_count=normal_count,
        anomaly_count=anomaly_count,
    )
