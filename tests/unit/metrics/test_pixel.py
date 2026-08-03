from __future__ import annotations

import numpy as np
import pytest

from experiments.metrics.pixel import compute_pixel_metrics


def one_region_masks() -> np.ndarray:
    return np.array(
        [
            [[True, False], [False, False]],
            [[False, False], [False, False]],
        ],
        dtype=np.bool_,
    )


def test_pixel_metrics_match_perfect_hand_computed_fixture() -> None:
    result = compute_pixel_metrics(
        one_region_masks(),
        np.array(
            [
                [[0.9, 0.1], [0.2, 0.3]],
                [[0.4, 0.0], [0.05, 0.15]],
            ],
            dtype=np.float64,
        ),
    )

    assert result.auroc == pytest.approx(1.0)
    assert result.average_precision == pytest.approx(1.0)
    assert result.au_pro == pytest.approx(1.0)
    assert result.pro_fpr_limit == 0.30
    assert result.region_count == 1


def test_pixel_metrics_define_constant_scores_like_official_curve() -> None:
    result = compute_pixel_metrics(
        one_region_masks(),
        np.full((2, 2, 2), 0.5, dtype=np.float64),
    )

    assert result.auroc == pytest.approx(0.5)
    assert result.average_precision == pytest.approx(1 / 8)
    assert result.au_pro == pytest.approx(0.15)


def test_pixel_metrics_report_undefined_all_normal_case() -> None:
    masks = np.zeros((2, 2, 2), dtype=np.bool_)
    result = compute_pixel_metrics(masks, np.zeros_like(masks, dtype=np.float64))

    assert result.auroc is None
    assert result.average_precision is None
    assert result.au_pro is None
    assert result.region_count == 0


def test_pixel_metrics_reject_mismatched_image_order() -> None:
    with pytest.raises(ValueError, match="order"):
        compute_pixel_metrics(
            one_region_masks(),
            np.zeros((2, 2, 2), dtype=np.float64),
            mask_ids=("a", "b"),
            map_ids=("b", "a"),
        )


@pytest.mark.parametrize(
    ("masks", "maps", "message"),
    [
        (np.zeros((2, 2), dtype=np.bool_), np.zeros((2, 2)), "three-dimensional"),
        (np.zeros((1, 2, 2), dtype=np.bool_), np.zeros((2, 2, 2)), "same shape"),
        (np.zeros((1, 2, 2), dtype=np.int64), np.zeros((1, 2, 2)), "boolean"),
        (
            np.zeros((1, 2, 2), dtype=np.bool_),
            np.array([[[0.0, 0.0], [0.0, np.inf]]]),
            "finite",
        ),
    ],
)
def test_pixel_metrics_reject_invalid_inputs(
    masks: np.ndarray, maps: np.ndarray, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compute_pixel_metrics(masks, maps)
