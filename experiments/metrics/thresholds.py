from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from experiments.metrics.artifacts import ThresholdResult
from inspection_platform.contracts import InspectionDecision

NDArrayFloat = NDArray[np.float64]


def validate_finite_vector(scores: NDArrayFloat) -> NDArray[np.float64]:
    """Return a detached float64 score vector or reject invalid calibration input."""

    checked = np.asarray(scores, dtype=np.float64)
    if checked.ndim != 1:
        raise ValueError("scores must be one-dimensional")
    if checked.size == 0:
        raise ValueError("scores must not be empty")
    if not np.isfinite(checked).all():
        raise ValueError("scores must contain only finite values")
    return checked


def conformal_upper_threshold(scores: NDArrayFloat, alpha: float = 0.01) -> ThresholdResult:
    """Calibrate the frozen finite-sample upper quantile on normal validation scores."""

    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be finite and strictly between zero and one")
    checked = validate_finite_vector(scores)
    rank = min(len(checked), math.ceil((len(checked) + 1) * (1 - alpha)))
    threshold = float(np.partition(checked, rank - 1)[rank - 1])
    review_rate = float(np.count_nonzero(checked >= threshold) / len(checked))
    return ThresholdResult(
        alpha=alpha,
        rank=rank,
        n=len(checked),
        threshold=threshold,
        achieved_validation_review_rate=review_rate,
    )


def decision_for_score(*, score: float, threshold: float) -> InspectionDecision:
    """Apply the immutable operating rule: values at the threshold require review."""

    if not math.isfinite(score) or not math.isfinite(threshold):
        raise ValueError("score and threshold must be finite")
    if score >= threshold:
        return InspectionDecision.REVIEW
    return InspectionDecision.PASS
