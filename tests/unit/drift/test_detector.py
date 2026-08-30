from __future__ import annotations

import numpy as np
import pytest

from inspection_platform.drift import compute_score_drift, population_stability_index


def test_identical_score_distributions_have_zero_psi() -> None:
    scores = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float64)

    result = compute_score_drift(scores, scores.copy(), bins=4)

    assert result.psi == 0.0
    assert result.severity == "low"
    assert result.baseline.count == 4
    assert result.current.count == 4
    assert population_stability_index(scores, scores.copy(), bins=4) == 0.0


def test_shifted_distribution_has_high_heuristic_severity() -> None:
    baseline = np.linspace(0.0, 1.0, 100, dtype=np.float64)
    current = np.linspace(2.0, 3.0, 100, dtype=np.float64)

    result = compute_score_drift(baseline, current, bins=10)

    assert result.psi >= 0.25
    assert result.severity == "high"
    assert result.sample_size_adequate


def test_psi_matches_hand_computed_two_bin_fixture() -> None:
    result = compute_score_drift(
        np.array([0.0, 1.0, 2.0, 3.0]),
        np.array([0.0, 0.0, 0.0, 3.0]),
        bins=2,
    )

    assert result.psi == pytest.approx(0.27465307216702745)


def test_duplicate_quantiles_reduce_effective_bins_deterministically() -> None:
    baseline = np.array(([0.0] * 20) + ([1.0] * 20), dtype=np.float64)

    first = compute_score_drift(baseline, baseline.copy(), bins=10)
    second = compute_score_drift(baseline, baseline.copy(), bins=10)

    assert first == second
    assert first.strategy == "baseline_quantiles"
    assert first.effective_bins < first.requested_bins
    assert first.psi == 0.0


def test_nonconstant_duplicate_quantiles_keep_a_distinguishing_edge() -> None:
    baseline = np.array(([0.0] * 9) + [1.0], dtype=np.float64)
    current = np.full(10, 2.0, dtype=np.float64)

    result = compute_score_drift(baseline, current, bins=2)

    assert result.strategy == "baseline_quantiles"
    assert result.effective_bins == 2
    assert result.severity == "high"


def test_constant_baseline_uses_three_way_bins() -> None:
    baseline = np.full(20, 0.5, dtype=np.float64)

    identical = compute_score_drift(baseline, baseline.copy(), bins=10)
    shifted = compute_score_drift(baseline, np.full(20, 0.6), bins=10)

    assert identical.strategy == "constant_baseline_three_way"
    assert identical.effective_bins == 3
    assert identical.psi == 0.0
    assert shifted.severity == "high"
    assert [item.current_count for item in shifted.histogram] == [0, 0, 20]


def test_constant_baseline_summary_is_canonical_for_inexact_float() -> None:
    baseline = np.full(3, 0.1, dtype=np.float64)

    result = compute_score_drift(baseline, baseline.copy())

    assert result.baseline.mean == 0.1
    assert result.baseline.standard_deviation == 0.0
    assert result.baseline.q1 == result.baseline.median == result.baseline.q3 == 0.1


def test_small_samples_cap_quantile_bins_and_are_marked_inadequate() -> None:
    result = compute_score_drift(
        np.array([0.0, 0.5, 1.0]),
        np.array([0.0, 0.5, 1.0]),
        bins=10,
    )

    assert result.effective_bins <= 3
    assert not result.sample_size_adequate


def test_finite_scores_that_overflow_summary_are_rejected() -> None:
    maximum = np.finfo(np.float64).max
    scores = np.array([maximum / 2, maximum], dtype=np.float64)

    with pytest.raises(ValueError, match="finite summary"):
        compute_score_drift(scores, scores)


def test_complex_scores_are_rejected_before_float_conversion() -> None:
    scores = np.array([0.1 + 0.2j, 0.3 + 0.4j])

    with pytest.raises(ValueError, match="real-valued"):
        compute_score_drift(scores, scores)


@pytest.mark.parametrize(
    ("baseline", "current", "message"),
    [
        (np.array([]), np.array([0.1]), "non-empty"),
        (np.array([0.1]), np.array([]), "non-empty"),
        (np.array([[0.1, 0.2]]), np.array([0.1, 0.2]), "one-dimensional"),
        (np.array([0.1, 0.2]), np.array([[0.1, 0.2]]), "one-dimensional"),
        (np.array([0.1, np.nan]), np.array([0.1, 0.2]), "finite"),
        (np.array([0.1, 0.2]), np.array([0.1, np.inf]), "finite"),
    ],
)
def test_invalid_score_arrays_are_rejected(
    baseline: np.ndarray, current: np.ndarray, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compute_score_drift(baseline, current)


@pytest.mark.parametrize("bins", [True, 1, 0, -1, 2.5])
def test_invalid_bin_counts_are_rejected(bins: object) -> None:
    scores = np.array([0.1, 0.2], dtype=np.float64)

    with pytest.raises(ValueError, match="bins"):
        compute_score_drift(scores, scores, bins=bins)  # type: ignore[arg-type]
