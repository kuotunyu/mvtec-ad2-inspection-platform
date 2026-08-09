from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from experiments.models.base import ArtifactFile, PredictionArtifact
from experiments.submission.thresholds import (
    calibrate_submission_threshold,
    combine_population_statistics,
)
from experiments.train import write_contract
from inspection_platform.contracts import PredictionRecord, sha256_file


def test_combined_statistics_match_literal_population_values() -> None:
    first = np.array([[0.0, 1.0]], dtype=np.float32)
    second = np.array([[2.0, 3.0]], dtype=np.float32)

    result = combine_population_statistics((first, second))

    assert result.pixel_count == 4
    assert result.mean == pytest.approx(1.5)
    assert result.standard_deviation == pytest.approx(np.sqrt(1.25))
    assert result.threshold == pytest.approx(1.5 + 3 * np.sqrt(1.25))


@pytest.mark.parametrize(
    "values",
    [
        np.array([], dtype=np.float32),
        np.array([0.0, 1.0], dtype=np.float32),
        np.array([[0.0, np.nan]], dtype=np.float32),
        np.array([[0.0, np.inf]], dtype=np.float32),
    ],
)
def test_combined_statistics_reject_invalid_maps(values: np.ndarray) -> None:
    with pytest.raises(ValueError, match="non-empty finite 2D"):
        combine_population_statistics((values,))


def _completed_run(
    tmp_path: Path,
    *,
    values: tuple[np.ndarray, ...] = (
        np.array([[0.0, 1.0]], dtype=np.float32),
        np.array([[2.0, 3.0]], dtype=np.float32),
    ),
    seed: int = 42,
    status: str = "completed",
) -> tuple[Path, tuple[Path, ...]]:
    run_identity = "1" * 64
    run_dir = tmp_path / run_identity
    map_root = run_dir / "predictions" / "validation-maps"
    map_root.mkdir(parents=True)
    maps: list[ArtifactFile] = []
    records: list[PredictionRecord] = []
    paths: list[Path] = []
    for index, array in enumerate(values):
        path = map_root / f"{index:06d}.npy"
        with path.open("xb") as stream:
            np.save(stream, array, allow_pickle=False)
        digest = sha256_file(path)
        paths.append(path)
        maps.append(ArtifactFile(path=path, sha256=digest, size=path.stat().st_size))
        records.append(
            PredictionRecord(
                input_id=f"{index:06d}:input.png",
                input_sha256="2" * 64,
                category="can",
                anomaly_score=float(np.nanmax(array)) if array.size else 0.0,
                anomaly_map_sha256=digest,
                model_bundle_id=f"run:{run_identity}",
                input_path=tmp_path / f"input-{index}.png",
            )
        )
    artifact = PredictionArtifact(
        family="patchcore",
        category="can",
        split="validation",
        config_sha256="3" * 64,
        records=tuple(records),
        anomaly_maps=tuple(maps),
    )
    write_contract(run_dir / "predictions" / "validation.json", artifact)
    spec = {"category": "can", "model_family": "patchcore", "seed": seed}
    (run_dir / "spec.json").write_text(json.dumps(spec, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "record.json").write_text(
        json.dumps({"status": status, "spec": spec}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_dir, tuple(paths)


def test_calibration_is_hash_bound_to_completed_seed42_validation_maps(tmp_path: Path) -> None:
    run_dir, _paths = _completed_run(tmp_path)
    validation_path = run_dir / "predictions" / "validation.json"

    result = calibrate_submission_threshold(run_dir)

    assert result.category == "can"
    assert result.run_identity == "1" * 64
    assert result.validation_artifact_sha256 == sha256_file(validation_path)
    assert result.pixel_count == 4
    assert result.mean == pytest.approx(1.5)
    assert result.standard_deviation == pytest.approx(np.sqrt(1.25))
    assert result.threshold == pytest.approx(1.5 + 3 * np.sqrt(1.25))
    assert len(result.identity) == 64


def test_calibration_rejects_changed_validation_map(tmp_path: Path) -> None:
    run_dir, paths = _completed_run(tmp_path)
    with paths[0].open("wb") as stream:
        np.save(stream, np.array([[9.0, 9.0]], dtype=np.float32), allow_pickle=False)

    with pytest.raises(ValueError, match="hash"):
        calibrate_submission_threshold(run_dir)


@pytest.mark.parametrize(
    ("seed", "status", "message"),
    [(7, "completed", "seed-42"), (42, "failed", "completed")],
)
def test_calibration_requires_completed_seed42_run(
    tmp_path: Path, seed: int, status: str, message: str
) -> None:
    run_dir, _paths = _completed_run(tmp_path, seed=seed, status=status)

    with pytest.raises(ValueError, match=message):
        calibrate_submission_threshold(run_dir)
