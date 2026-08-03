from __future__ import annotations

import numpy as np
import pytest

from experiments.metrics.image import compute_image_metrics


def test_image_metrics_match_hand_computed_fixture() -> None:
    result = compute_image_metrics(
        np.array([0, 0, 1, 1], dtype=np.int64),
        np.array([0.1, 0.4, 0.35, 0.8], dtype=np.float64),
    )

    assert result.auroc == pytest.approx(0.75)
    assert result.average_precision == pytest.approx(5 / 6)
    assert result.normal_count == 2
    assert result.anomaly_count == 2


def test_image_metrics_define_constant_scores() -> None:
    result = compute_image_metrics(
        np.array([0, 1], dtype=np.int64),
        np.array([0.5, 0.5], dtype=np.float64),
    )

    assert result.auroc == pytest.approx(0.5)
    assert result.average_precision == pytest.approx(0.5)


def test_image_metrics_report_undefined_all_normal_case() -> None:
    result = compute_image_metrics(
        np.array([0, 0, 0], dtype=np.int64),
        np.array([0.1, 0.2, 0.3], dtype=np.float64),
    )

    assert result.auroc is None
    assert result.average_precision is None
    assert result.normal_count == 3
    assert result.anomaly_count == 0


@pytest.mark.parametrize(
    ("labels", "scores", "message"),
    [
        (np.array([[0, 1]]), np.array([0.1, 0.9]), "one-dimensional"),
        (np.array([0, 1]), np.array([[0.1, 0.9]]), "one-dimensional"),
        (np.array([0]), np.array([0.1, 0.9]), "same length"),
        (np.array([0, 2]), np.array([0.1, 0.9]), "binary"),
        (np.array([0, 1]), np.array([0.1, np.nan]), "finite"),
    ],
)
def test_image_metrics_reject_invalid_inputs(
    labels: np.ndarray, scores: np.ndarray, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compute_image_metrics(labels, scores)
