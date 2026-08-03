from __future__ import annotations

import numpy as np
import pytest

from experiments.metrics.bootstrap import paired_bootstrap_delta


def test_paired_bootstrap_matches_constant_hand_computed_delta() -> None:
    result = paired_bootstrap_delta(
        np.array([1.0, 2.0, 3.0]),
        np.array([0.0, 1.0, 2.0]),
        seed=42,
        resamples=1_000,
    )

    assert result.estimate == 1.0
    assert result.lower == 1.0
    assert result.upper == 1.0
    assert result.seed == 42
    assert result.resamples == 1_000


def test_paired_bootstrap_is_deterministic_for_seed() -> None:
    left = np.array([0.2, 0.8, 0.5, 0.9])
    right = np.array([0.1, 0.7, 0.7, 0.4])

    first = paired_bootstrap_delta(left, right, seed=7, resamples=257)
    second = paired_bootstrap_delta(left, right, seed=7, resamples=257)

    assert first == second


@pytest.mark.parametrize(
    ("left", "right", "message"),
    [
        (np.array([]), np.array([]), "empty"),
        (np.array([[1.0]]), np.array([1.0]), "one-dimensional"),
        (np.array([1.0]), np.array([1.0, 2.0]), "same length"),
        (np.array([1.0]), np.array([np.nan]), "finite"),
    ],
)
def test_paired_bootstrap_rejects_invalid_samples(
    left: np.ndarray, right: np.ndarray, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        paired_bootstrap_delta(left, right, seed=1, resamples=10)


def test_paired_bootstrap_rejects_non_positive_resamples() -> None:
    with pytest.raises(ValueError, match="resamples"):
        paired_bootstrap_delta(np.array([1.0]), np.array([0.0]), seed=1, resamples=0)
