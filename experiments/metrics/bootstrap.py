from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from experiments.metrics.artifacts import ConfidenceInterval

NDArrayFloat = NDArray[np.float64]
_BOOTSTRAP_BATCH_SIZE = 1_024


def paired_bootstrap_delta(
    left: NDArrayFloat,
    right: NDArrayFloat,
    seed: int,
    resamples: int = 10_000,
) -> ConfidenceInterval:
    """Bootstrap the paired mean of ``left - right`` using bounded memory."""

    checked_left = np.asarray(left, dtype=np.float64)
    checked_right = np.asarray(right, dtype=np.float64)
    if checked_left.ndim != 1 or checked_right.ndim != 1:
        raise ValueError("paired samples must be one-dimensional")
    if checked_left.size == 0 or checked_right.size == 0:
        raise ValueError("paired samples must not be empty")
    if len(checked_left) != len(checked_right):
        raise ValueError("paired samples must have the same length")
    if not np.isfinite(checked_left).all() or not np.isfinite(checked_right).all():
        raise ValueError("paired samples must contain only finite values")
    if resamples <= 0:
        raise ValueError("resamples must be positive")

    differences = checked_left - checked_right
    generator = np.random.default_rng(seed)
    bootstrap_means = np.empty(resamples, dtype=np.float64)
    for start in range(0, resamples, _BOOTSTRAP_BATCH_SIZE):
        stop = min(start + _BOOTSTRAP_BATCH_SIZE, resamples)
        indices = generator.integers(0, len(differences), size=(stop - start, len(differences)))
        bootstrap_means[start:stop] = differences[indices].mean(axis=1)

    lower, upper = np.quantile(bootstrap_means, (0.025, 0.975), method="linear")
    return ConfidenceInterval(
        estimate=float(differences.mean()),
        lower=float(lower),
        upper=float(upper),
        seed=seed,
        resamples=resamples,
    )
