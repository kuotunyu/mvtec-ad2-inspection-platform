from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from experiments.metrics import ConfidenceInterval, ImageMetrics, MetricArtifact, PixelMetrics
from experiments.metrics.official import official_au_pro
from experiments.metrics.pixel import compute_pixel_metrics

OFFICIAL_PARITY_ABS_TOL = 1e-7


def test_metric_artifact_retains_categories_and_rejects_mixed_prediction_contracts() -> None:
    image = ImageMetrics(auroc=1.0, average_precision=1.0, normal_count=1, anomaly_count=1)
    pixel = PixelMetrics(
        auroc=1.0,
        average_precision=1.0,
        au_pro=1.0,
        pro_fpr_limit=0.3,
        normal_pixel_count=3,
        anomaly_pixel_count=1,
        region_count=1,
    )

    artifact = MetricArtifact(
        prediction_contract_versions=("1.0.0",),
        category_metrics={"can": {"image": image, "pixel": pixel}},
    )

    assert artifact.metric_contract_version == "1.0.0"
    assert artifact.category_metrics["can"].image.auroc == 1.0

    with pytest.raises(ValidationError, match="mixed prediction-contract versions"):
        MetricArtifact(
            prediction_contract_versions=("1.0.0", "1.1.0"),
            category_metrics={"can": {"image": image, "pixel": pixel}},
        )


def test_metric_contracts_reject_internally_inconsistent_evidence() -> None:
    with pytest.raises(ValidationError, match="defined when both classes"):
        ImageMetrics(
            auroc=None,
            average_precision=None,
            normal_count=1,
            anomaly_count=1,
        )

    with pytest.raises(ValidationError, match="lower must not exceed upper"):
        ConfidenceInterval(
            estimate=0.0,
            lower=0.2,
            upper=-0.2,
            seed=1,
            resamples=100,
        )

    with pytest.raises(ValidationError, match="frozen value"):
        PixelMetrics(
            auroc=None,
            average_precision=None,
            au_pro=None,
            pro_fpr_limit=0.2,
            normal_pixel_count=4,
            anomaly_pixel_count=0,
            region_count=0,
        )


@pytest.mark.dataset
def test_au_pro_matches_verified_official_utility_on_synthetic_masks() -> None:
    official_root_text = os.environ.get("MVTEC_AD_EVALUATION_ROOT")
    if official_root_text is None:
        pytest.skip("MVTEC_AD_EVALUATION_ROOT is required for official AU-PRO parity")

    masks = np.array(
        [
            [[True, True, False], [False, False, False]],
            [[False, False, False], [False, True, False]],
        ],
        dtype=np.bool_,
    )
    maps = np.array(
        [
            [[0.9, 0.7, 0.1], [0.2, 0.8, 0.0]],
            [[0.3, 0.4, 0.6], [0.05, 0.65, 0.15]],
        ],
        dtype=np.float64,
    )

    ours = compute_pixel_metrics(masks, maps).au_pro
    official = official_au_pro(Path(official_root_text), masks, maps, fpr_limit=0.30)

    assert ours is not None
    assert ours == pytest.approx(official, abs=OFFICIAL_PARITY_ABS_TOL)
