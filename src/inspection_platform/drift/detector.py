from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

PSI_EPSILON = 1e-6
PSI_MODERATE_THRESHOLD = 0.1
PSI_HIGH_THRESHOLD = 0.25
MIN_EXPECTED_SAMPLES_PER_BIN = 5

DriftSeverity = Literal["low", "moderate", "high"]
BinStrategy = Literal["baseline_quantiles", "constant_baseline_three_way"]


@dataclass(frozen=True, slots=True)
class ScoreSummary:
    count: int
    minimum: float
    maximum: float
    mean: float
    standard_deviation: float
    q1: float
    median: float
    q3: float


@dataclass(frozen=True, slots=True)
class HistogramBin:
    label: str
    lower_bound: float | None
    upper_bound: float | None
    baseline_count: int
    current_count: int
    baseline_share: float
    current_share: float


@dataclass(frozen=True, slots=True)
class DriftResult:
    baseline: ScoreSummary
    current: ScoreSummary
    requested_bins: int
    effective_bins: int
    strategy: BinStrategy
    epsilon: float
    histogram: tuple[HistogramBin, ...]
    psi: float
    severity: DriftSeverity
    sample_size_adequate: bool


def _validated_scores(name: str, values: ArrayLike) -> NDArray[np.float64]:
    if np.iscomplexobj(values):
        raise ValueError(f"{name} scores must be real-valued")
    scores = np.asarray(values, dtype=np.float64)
    if scores.ndim != 1:
        raise ValueError(f"{name} scores must be one-dimensional")
    if scores.size == 0:
        raise ValueError(f"{name} scores must be non-empty")
    if not np.isfinite(scores).all():
        raise ValueError(f"{name} scores must be finite")
    return scores


def _score_summary(scores: NDArray[np.float64]) -> ScoreSummary:
    minimum = float(np.min(scores))
    maximum = float(np.max(scores))
    if minimum == maximum:
        return ScoreSummary(
            count=int(scores.size),
            minimum=minimum,
            maximum=maximum,
            mean=minimum,
            standard_deviation=0.0,
            q1=minimum,
            median=minimum,
            q3=minimum,
        )
    with np.errstate(invalid="ignore", over="ignore"):
        q1, median, q3 = np.quantile(scores, (0.25, 0.5, 0.75), method="linear")
        mean = np.mean(scores)
        standard_deviation = np.std(scores, ddof=0)
    derived = np.array((mean, standard_deviation, q1, median, q3), dtype=np.float64)
    if not np.isfinite(derived).all():
        raise ValueError("scores must produce a finite summary")
    return ScoreSummary(
        count=int(scores.size),
        minimum=minimum,
        maximum=maximum,
        mean=float(mean),
        standard_deviation=float(standard_deviation),
        q1=float(q1),
        median=float(median),
        q3=float(q3),
    )


def _constant_counts(scores: NDArray[np.float64], value: float) -> NDArray[np.int64]:
    return np.array(
        [
            np.count_nonzero(scores < value),
            np.count_nonzero(scores == value),
            np.count_nonzero(scores > value),
        ],
        dtype=np.int64,
    )


def _quantile_counts(
    baseline: NDArray[np.float64], current: NDArray[np.float64], bins: int
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]:
    capped_bins = min(bins, int(baseline.size))
    quantiles = np.linspace(0.0, 1.0, capped_bins + 1, dtype=np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        raw_edges = np.quantile(baseline, quantiles, method="linear")
    if not np.isfinite(raw_edges).all():
        raise ValueError("baseline scores must produce finite quantile edges")
    minimum = raw_edges[0]
    maximum = raw_edges[-1]
    interior = np.unique(raw_edges[1:-1])
    interior = interior[(interior > minimum) & (interior < maximum)]
    if interior.size == 0:
        interior = np.array([maximum], dtype=np.float64)
    edges = np.concatenate((np.array([-np.inf]), interior, np.array([np.inf]))).astype(
        np.float64, copy=False
    )
    baseline_counts = np.histogram(baseline, bins=edges)[0].astype(np.int64, copy=False)
    current_counts = np.histogram(current, bins=edges)[0].astype(np.int64, copy=False)
    return baseline_counts, current_counts, edges


def _stabilized_shares(counts: NDArray[np.int64], total: int) -> NDArray[np.float64]:
    shares = counts.astype(np.float64) / total
    shares = np.maximum(shares, PSI_EPSILON)
    return shares / np.sum(shares)


def _severity(psi: float) -> DriftSeverity:
    if psi < PSI_MODERATE_THRESHOLD:
        return "low"
    if psi < PSI_HIGH_THRESHOLD:
        return "moderate"
    return "high"


def compute_score_drift(
    baseline: ArrayLike,
    current: ArrayLike,
    bins: int = 10,
) -> DriftResult:
    """Compare two one-dimensional anomaly-score distributions using PSI.

    Severity bands are conventional heuristics, not calibrated production gates.
    Quantile bins are capped by baseline sample count and duplicate interior edges
    are removed. A constant baseline uses explicit below/equal/above buckets.
    """

    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 2:
        raise ValueError("bins must be an integer greater than or equal to 2")
    baseline_scores = _validated_scores("baseline", baseline)
    current_scores = _validated_scores("current", current)
    bounds: tuple[tuple[float | None, float | None], ...]
    labels: tuple[str, ...]

    if np.all(baseline_scores == baseline_scores[0]):
        constant = float(baseline_scores[0])
        baseline_counts = _constant_counts(baseline_scores, constant)
        current_counts = _constant_counts(current_scores, constant)
        bounds = ((None, constant), (constant, constant), (constant, None))
        labels = (
            "below_baseline_constant",
            "equal_to_baseline_constant",
            "above_baseline_constant",
        )
        strategy: BinStrategy = "constant_baseline_three_way"
    else:
        baseline_counts, current_counts, edges = _quantile_counts(
            baseline_scores, current_scores, bins
        )
        bounds = tuple(
            (
                None if np.isneginf(edges[index]) else float(edges[index]),
                None if np.isposinf(edges[index + 1]) else float(edges[index + 1]),
            )
            for index in range(edges.size - 1)
        )
        labels = tuple(f"bin_{index}" for index in range(len(bounds)))
        strategy = "baseline_quantiles"

    baseline_shares = baseline_counts.astype(np.float64) / baseline_scores.size
    current_shares = current_counts.astype(np.float64) / current_scores.size
    stabilized_baseline = _stabilized_shares(baseline_counts, int(baseline_scores.size))
    stabilized_current = _stabilized_shares(current_counts, int(current_scores.size))
    psi = max(
        0.0,
        float(
            np.sum(
                (stabilized_current - stabilized_baseline)
                * np.log(stabilized_current / stabilized_baseline)
            )
        ),
    )
    histogram = tuple(
        HistogramBin(
            label=label,
            lower_bound=lower,
            upper_bound=upper,
            baseline_count=int(baseline_counts[index]),
            current_count=int(current_counts[index]),
            baseline_share=float(baseline_shares[index]),
            current_share=float(current_shares[index]),
        )
        for index, (label, (lower, upper)) in enumerate(zip(labels, bounds, strict=True))
    )
    effective_bins = len(histogram)
    sample_size_adequate = min(baseline_scores.size, current_scores.size) >= (
        MIN_EXPECTED_SAMPLES_PER_BIN * effective_bins
    )
    return DriftResult(
        baseline=_score_summary(baseline_scores),
        current=_score_summary(current_scores),
        requested_bins=bins,
        effective_bins=effective_bins,
        strategy=strategy,
        epsilon=PSI_EPSILON,
        histogram=histogram,
        psi=psi,
        severity=_severity(psi),
        sample_size_adequate=bool(sample_size_adequate),
    )


def population_stability_index(
    baseline: ArrayLike,
    current: ArrayLike,
    bins: int = 10,
) -> float:
    """Return PSI while applying the same validation and binning as the full result."""

    return compute_score_drift(baseline, current, bins=bins).psi


__all__ = [
    "DriftResult",
    "HistogramBin",
    "ScoreSummary",
    "compute_score_drift",
    "population_stability_index",
]
