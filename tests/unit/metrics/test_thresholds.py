from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from experiments.metrics import ThresholdResult
from experiments.metrics.thresholds import conformal_upper_threshold, decision_for_score
from inspection_platform.contracts import InspectionDecision


def test_conformal_threshold_uses_finite_sample_rank() -> None:
    scores = np.arange(100, dtype=float)

    result = conformal_upper_threshold(scores, alpha=0.01)

    assert result.rank == 100
    assert result.threshold == 99.0
    assert result.n == 100
    assert result.achieved_validation_review_rate == 0.01


def test_threshold_ties_are_review() -> None:
    assert decision_for_score(score=0.7, threshold=0.7) is InspectionDecision.REVIEW
    assert decision_for_score(score=0.69, threshold=0.7) is InspectionDecision.PASS


@pytest.mark.parametrize(
    ("scores", "message"),
    [
        (np.array([], dtype=float), "empty"),
        (np.array([[0.1, 0.2]], dtype=float), "one-dimensional"),
        (np.array([0.1, np.nan]), "finite"),
        (np.array([0.1, np.inf]), "finite"),
    ],
)
def test_conformal_threshold_rejects_invalid_scores(
    scores: np.ndarray[tuple[int, ...], np.dtype[np.float64]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        conformal_upper_threshold(scores)


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.0, 1.1, np.nan])
def test_conformal_threshold_rejects_invalid_alpha(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha"):
        conformal_upper_threshold(np.array([0.1, 0.2]), alpha=alpha)


@pytest.mark.parametrize(("score", "threshold"), [(np.nan, 0.5), (0.5, np.inf)])
def test_decision_rejects_non_finite_values(score: float, threshold: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        decision_for_score(score=score, threshold=threshold)


def test_threshold_contract_rejects_rank_above_sample_count() -> None:
    with pytest.raises(ValidationError, match="rank must not exceed"):
        ThresholdResult(
            alpha=0.01,
            rank=2,
            n=1,
            threshold=0.5,
            achieved_validation_review_rate=1.0,
        )
