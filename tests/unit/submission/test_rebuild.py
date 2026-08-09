from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image

from experiments.submission.build import (
    PrivateManifest,
    PublicBoundaryError,
    SubmissionPrediction,
)
from experiments.submission.rebuild import (
    cached_predictions,
    frozen_champion_run,
    rebuild_cached_submission,
    validate_rebuild_output,
)
from experiments.submission.thresholds import SubmissionThreshold
from inspection_platform.contracts import sha256_file


def _one_image_cache(tmp_path: Path) -> tuple[PrivateManifest, Path, Path, Path]:
    dataset_root = tmp_path / "dataset"
    source = dataset_root / "can" / "test_private" / "000_regular.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (3, 2), color=(0, 0, 0)).save(source)
    cache_root = tmp_path / "prediction-cache"
    tiff = cache_root / "can" / "test_private" / "tiff" / "000_regular.tiff"
    tiff.parent.mkdir(parents=True)
    tifffile.imwrite(tiff, np.zeros((2, 3), dtype=np.float16))
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    return manifest, dataset_root, cache_root, tiff


def test_cached_predictions_match_exact_manifest_and_geometry(tmp_path: Path) -> None:
    manifest, dataset_root, cache_root, tiff = _one_image_cache(tmp_path)

    predictions = cached_predictions(
        manifest=manifest,
        cache_root=cache_root,
        dataset_root=dataset_root,
    )

    assert predictions == (
        SubmissionPrediction(
            category="can",
            split="test_private",
            image_id="000_regular",
            anomaly_map=tiff.resolve(),
        ),
    )


def test_cached_predictions_reject_missing_tiff(tmp_path: Path) -> None:
    manifest, dataset_root, cache_root, tiff = _one_image_cache(tmp_path)
    tiff.unlink()

    with pytest.raises(ValueError, match="missing cached TIFF"):
        cached_predictions(
            manifest=manifest,
            cache_root=cache_root,
            dataset_root=dataset_root,
        )


def test_cached_predictions_reject_spurious_identity(tmp_path: Path) -> None:
    manifest, dataset_root, cache_root, tiff = _one_image_cache(tmp_path)
    tifffile.imwrite(tiff.with_name("999_extra.tiff"), np.zeros((2, 3), dtype=np.float16))

    with pytest.raises(ValueError, match="extra cached TIFF"):
        cached_predictions(
            manifest=manifest,
            cache_root=cache_root,
            dataset_root=dataset_root,
        )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (np.zeros((3, 2), dtype=np.float16), "geometry"),
        (np.zeros((2, 3), dtype=np.float32), "float16"),
        (np.array([[0.0, np.nan, 0.0], [0.0, 0.0, 0.0]], dtype=np.float16), "finite"),
    ],
)
def test_cached_predictions_reject_invalid_tiff(
    tmp_path: Path,
    values: np.ndarray,
    message: str,
) -> None:
    manifest, dataset_root, cache_root, tiff = _one_image_cache(tmp_path)
    tifffile.imwrite(tiff, values)

    with pytest.raises(ValueError, match=message):
        cached_predictions(
            manifest=manifest,
            cache_root=cache_root,
            dataset_root=dataset_root,
        )


def test_rebuild_uses_cache_without_gpu_and_runs_validator_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, dataset_root, cache_root, _tiff = _one_image_cache(tmp_path)
    predictions = cached_predictions(
        manifest=manifest,
        cache_root=cache_root,
        dataset_root=dataset_root,
    )
    threshold = SubmissionThreshold(
        category="can",
        run_identity="1" * 64,
        validation_artifact_sha256="2" * 64,
        pixel_count=10,
        mean=0.5,
        standard_deviation=0.0,
        threshold=0.5,
    )
    original_archive = tmp_path / "original-private-submission.tar.gz"
    original_archive.write_bytes(b"immutable-original")
    original_sha256 = sha256_file(original_archive)
    validated: list[Path] = []

    class ForbiddenGpuLease:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("cache-only rebuild acquired the GPU lease")

    monkeypatch.setattr("experiments.submission.build.GpuLease", ForbiddenGpuLease)

    def validate(submission_dir: Path) -> None:
        validated.append(submission_dir)
        assert (
            submission_dir / "anomaly_images" / "can" / "test_private" / "000_regular.tiff"
        ).is_file()
        assert (
            submission_dir
            / "anomaly_images_thresholded"
            / "can"
            / "test_private"
            / "000_regular.png"
        ).is_file()

    output_root = tmp_path / "corrected-output"
    archive = rebuild_cached_submission(
        manifest=manifest,
        predictions=predictions,
        thresholds={"can": threshold},
        output_root=output_root,
        validate=validate,
    )

    assert archive == output_root.resolve() / "private_submission.tar.gz"
    assert validated and validated[0].name == "private_submission"
    assert sha256_file(original_archive) == original_sha256
    calibration = json.loads(
        (output_root / "calibrations" / "can.json").read_text(encoding="utf-8")
    )
    assert calibration["identity"] == threshold.identity
    summary = json.loads((output_root / "submission_summary.json").read_text(encoding="utf-8"))
    assert summary["validator_status"] == "LOCAL-PREFLIGHT-NOT-SUBMITTED"
    assert summary["continuous_image_count"] == 1
    assert summary["thresholded_image_count"] == 1


@pytest.mark.parametrize("location", ["repo", "source", "source-child", "source-parent"])
def test_rebuild_output_must_not_overlap_inputs(tmp_path: Path, location: str) -> None:
    repository = tmp_path / "repo"
    source_cache = tmp_path / "external" / "prediction-cache"
    repository.mkdir()
    source_cache.mkdir(parents=True)
    outputs = {
        "repo": repository / "private-output",
        "source": source_cache,
        "source-child": source_cache / "corrected",
        "source-parent": source_cache.parent,
    }

    with pytest.raises(PublicBoundaryError, match=r"repository|source cache"):
        validate_rebuild_output(
            output_root=outputs[location],
            source_cache_root=source_cache,
            repository_root=repository,
        )


def test_frozen_champion_run_ignores_same_seed_distractor(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    approved_identity = "a" * 64
    distractor_identity = "b" * 64
    for identity in (approved_identity, distractor_identity):
        run = runs_root / identity
        run.mkdir(parents=True)
        spec = {"category": "can", "model_family": "patchcore", "seed": 42}
        (run / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        (run / "record.json").write_text(
            json.dumps({"status": "completed", "spec": spec}),
            encoding="utf-8",
        )

    selected = frozen_champion_run(
        runs_root=runs_root,
        category="can",
        family="patchcore",
        run_identities=(approved_identity,),
    )

    assert selected == (runs_root / approved_identity).resolve()
