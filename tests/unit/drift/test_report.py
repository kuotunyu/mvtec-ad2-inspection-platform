from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from experiments.drift import DriftReport, build_drift_report
from experiments.models.base import ArtifactFile, PredictionArtifact, PredictionSplit
from experiments.train import write_contract
from inspection_platform.contracts import PredictionRecord, sha256_file
from inspection_platform.contracts.dataset import MVTecAD2Category


def _prediction_artifact(
    category: MVTecAD2Category,
    split: PredictionSplit,
    scores: tuple[float, ...],
    *,
    bundle_id: str | None = None,
    config_sha256: str = "a" * 64,
    record_category: MVTecAD2Category | None = None,
) -> PredictionArtifact:
    records: list[PredictionRecord] = []
    maps: list[ArtifactFile] = []
    for index, score in enumerate(scores):
        map_digest = f"{index + 1:064x}"
        maps.append(ArtifactFile(path=Path(f"map-{index}.npy"), sha256=map_digest, size=1))
        records.append(
            PredictionRecord(
                input_id=f"input-{index}",
                input_sha256=f"{index + 101:064x}",
                category=record_category or category,
                anomaly_score=score,
                anomaly_map_sha256=map_digest,
                model_bundle_id=(bundle_id if bundle_id is not None else f"champion-{category}"),
                input_path=Path(f"private-input-{category}-{index}.tiff"),
            )
        )
    return PredictionArtifact(
        family="patchcore",
        category=category,
        split=split,
        config_sha256=config_sha256,
        records=tuple(records),
        anomaly_maps=tuple(maps),
    )


def _write(path: Path, artifact: PredictionArtifact) -> Path:
    return write_contract(path, artifact)


def test_report_uses_prediction_artifact_scores_without_leaking_raw_records(
    tmp_path: Path,
) -> None:
    baseline = _write(
        tmp_path / "baseline.json",
        _prediction_artifact("can", "test_public", tuple(index / 20 for index in range(20))),
    )
    current = _write(
        tmp_path / "current.json",
        _prediction_artifact("can", "validation", tuple(1.0 + (index / 20) for index in range(20))),
    )

    report = build_drift_report(
        baseline_artifacts=(baseline,),
        current_artifacts=(current,),
        baseline_description="public standard-lighting prediction artifacts",
        current_description="sanitized alternate-lighting prediction artifacts",
        bins=5,
    )

    assert report.schema_version == "1.0.0"
    assert report.report_type == "offline_anomaly_score_distribution_drift"
    assert report.generator.version == "1.0.0"
    assert report.method.threshold_kind == "heuristic_not_calibrated_production_gate"
    assert report.baseline.sample_count == 20
    assert report.current.sample_count == 20
    assert report.baseline.artifacts[0].artifact_sha256 == sha256_file(baseline)
    assert report.comparisons[0].category == "can"
    assert report.comparisons[0].model_bundle_id == "champion-can"
    assert report.comparisons[0].psi >= 0.25
    assert report.comparisons[0].severity == "high"

    serialized = report.model_dump_json()
    assert "private-input" not in serialized
    assert '"records"' not in serialized
    assert '"anomaly_score"' not in serialized
    assert str(tmp_path) not in serialized


def test_report_is_deterministic_regardless_of_artifact_argument_order(tmp_path: Path) -> None:
    baseline_can = _write(
        tmp_path / "baseline-can.json",
        _prediction_artifact("can", "test_public", (0.1, 0.2, 0.3)),
    )
    baseline_vial = _write(
        tmp_path / "baseline-vial.json",
        _prediction_artifact("vial", "test_public", (0.2, 0.3, 0.4)),
    )
    current_can = _write(
        tmp_path / "current-can.json",
        _prediction_artifact("can", "validation", (0.1, 0.2, 0.3)),
    )
    current_vial = _write(
        tmp_path / "current-vial.json",
        _prediction_artifact("vial", "validation", (0.2, 0.3, 0.4)),
    )

    first = build_drift_report(
        baseline_artifacts=(baseline_vial, baseline_can),
        current_artifacts=(current_can, current_vial),
        baseline_description="baseline",
        current_description="current",
    )
    second = build_drift_report(
        baseline_artifacts=(baseline_can, baseline_vial),
        current_artifacts=(current_vial, current_can),
        baseline_description="baseline",
        current_description="current",
    )

    assert first == second
    assert [item.category for item in first.comparisons] == ["can", "vial"]


def test_report_rejects_mismatched_category_sets(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.json",
        _prediction_artifact("can", "test_public", (0.1, 0.2)),
    )
    current = _write(
        tmp_path / "current.json",
        _prediction_artifact("vial", "validation", (0.1, 0.2)),
    )

    with pytest.raises(ValueError, match="category sets"):
        build_drift_report(
            baseline_artifacts=(baseline,),
            current_artifacts=(current,),
            baseline_description="baseline",
            current_description="current",
        )


@pytest.mark.parametrize(
    ("config_sha256", "bundle_id", "message"),
    [
        ("b" * 64, None, "config"),
        ("a" * 64, "different-bundle", "bundle"),
    ],
)
def test_report_rejects_incomparable_model_identities(
    tmp_path: Path, config_sha256: str, bundle_id: str | None, message: str
) -> None:
    baseline = _write(
        tmp_path / "baseline.json",
        _prediction_artifact("can", "test_public", (0.1, 0.2)),
    )
    current = _write(
        tmp_path / "current.json",
        _prediction_artifact(
            "can",
            "validation",
            (0.1, 0.2),
            config_sha256=config_sha256,
            bundle_id=bundle_id,
        ),
    )

    with pytest.raises(ValueError, match=message):
        build_drift_report(
            baseline_artifacts=(baseline,),
            current_artifacts=(current,),
            baseline_description="baseline",
            current_description="current",
        )


def test_report_rejects_empty_or_internally_inconsistent_artifacts(tmp_path: Path) -> None:
    empty = _write(
        tmp_path / "empty.json",
        _prediction_artifact("can", "test_public", ()),
    )
    valid_current = _write(
        tmp_path / "current.json",
        _prediction_artifact("can", "validation", (0.1, 0.2)),
    )
    with pytest.raises(ValueError, match="records must be non-empty"):
        build_drift_report(
            baseline_artifacts=(empty,),
            current_artifacts=(valid_current,),
            baseline_description="baseline",
            current_description="current",
        )

    inconsistent = _write(
        tmp_path / "inconsistent.json",
        _prediction_artifact("can", "test_public", (0.1, 0.2), record_category="vial"),
    )
    with pytest.raises(ValueError, match="record category"):
        build_drift_report(
            baseline_artifacts=(inconsistent,),
            current_artifacts=(valid_current,),
            baseline_description="baseline",
            current_description="current",
        )


def test_report_rejects_duplicate_category_artifacts(tmp_path: Path) -> None:
    first = _write(
        tmp_path / "first.json",
        _prediction_artifact("can", "test_public", (0.1, 0.2)),
    )
    second = _write(
        tmp_path / "second.json",
        _prediction_artifact("can", "test_public", (0.1, 0.2)),
    )
    current = _write(
        tmp_path / "current.json",
        _prediction_artifact("can", "validation", (0.1, 0.2)),
    )

    with pytest.raises(ValueError, match="duplicate category"):
        build_drift_report(
            baseline_artifacts=(first, second),
            current_artifacts=(current,),
            baseline_description="baseline",
            current_description="current",
        )


def test_report_rejects_blank_model_bundle_identity(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.json",
        _prediction_artifact("can", "test_public", (0.1, 0.2), bundle_id=" "),
    )
    current = _write(
        tmp_path / "current.json",
        _prediction_artifact("can", "validation", (0.1, 0.2), bundle_id=" "),
    )

    with pytest.raises(ValueError, match="bundle identity must be non-blank"):
        build_drift_report(
            baseline_artifacts=(baseline,),
            current_artifacts=(current,),
            baseline_description="baseline",
            current_description="current",
        )


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("method_epsilon", "epsilon"),
        ("source_total", "source sample count"),
        ("summary_order", "ordered"),
        ("effective_bins", "effective_bins"),
        ("bin_strategy", "bin strategy"),
        ("bin_bounds", "histogram bounds"),
        ("psi", "PSI"),
        ("severity", "severity"),
    ],
)
def test_report_contract_rejects_corrupted_internal_claims(
    tmp_path: Path, corruption: str, message: str
) -> None:
    baseline = _write(
        tmp_path / "baseline.json",
        _prediction_artifact("can", "test_public", (0.0, 1.0, 2.0, 3.0)),
    )
    current = _write(
        tmp_path / "current.json",
        _prediction_artifact("can", "validation", (0.0, 0.0, 0.0, 3.0)),
    )
    report = build_drift_report(
        baseline_artifacts=(baseline,),
        current_artifacts=(current,),
        baseline_description="baseline",
        current_description="current",
        bins=2,
    )
    payload = report.model_dump(mode="json")
    comparison = payload["comparisons"][0]
    if corruption == "method_epsilon":
        payload["method"]["epsilon"] = -1.0
    elif corruption == "source_total":
        payload["baseline"]["sample_count"] += 1
    elif corruption == "summary_order":
        comparison["baseline"]["q1"] = comparison["baseline"]["maximum"] + 1.0
    elif corruption == "effective_bins":
        comparison["effective_bins"] += 1
    elif corruption == "bin_strategy":
        comparison["bin_strategy"] = "constant_baseline_three_way"
    elif corruption == "bin_bounds":
        comparison["histogram"][0]["upper_bound"] = 2.0
    elif corruption == "psi":
        comparison["psi"] = 0.0
    elif corruption == "severity":
        comparison["severity"] = "low"
    else:
        raise AssertionError(f"unknown corruption fixture: {corruption}")

    with pytest.raises(ValidationError, match=message):
        DriftReport.model_validate_json(json.dumps(payload))


def test_report_contract_rejects_corrupted_constant_baseline_bins(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.json",
        _prediction_artifact("can", "test_public", (0.5, 0.5, 0.5)),
    )
    current = _write(
        tmp_path / "current.json",
        _prediction_artifact("can", "validation", (0.4, 0.5, 0.6)),
    )
    report = build_drift_report(
        baseline_artifacts=(baseline,),
        current_artifacts=(current,),
        baseline_description="baseline",
        current_description="current",
    )
    payload = report.model_dump(mode="json")
    payload["comparisons"][0]["histogram"][1]["label"] = "bin_1"

    with pytest.raises(ValidationError, match="constant baseline histogram"):
        DriftReport.model_validate_json(json.dumps(payload))
