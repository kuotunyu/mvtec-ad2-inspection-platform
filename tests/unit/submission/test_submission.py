from __future__ import annotations

import tarfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image

from experiments.submission.build import (
    PrivateManifest,
    SubmissionBuilder,
    SubmissionPrediction,
    inspect_submission,
)
from experiments.submission.official_utils import OfficialUtilities
from experiments.submission.thresholds import SubmissionThreshold
from experiments.submission.verify import verify_archive, write_submission_summary


def _prediction(
    tmp_path: Path,
    *,
    image_id: str = "000_regular",
    values: np.ndarray | None = None,
) -> SubmissionPrediction:
    source = tmp_path / f"{image_id}.tiff"
    tifffile.imwrite(
        source,
        np.zeros((4, 4), dtype=np.float16) if values is None else values,
    )
    return SubmissionPrediction(
        category="can",
        split="test_private",
        image_id=image_id,
        anomaly_map=source,
    )


def _threshold(value: float, *, category: str = "can") -> SubmissionThreshold:
    return SubmissionThreshold(
        category=category,
        run_identity="1" * 64,
        validation_artifact_sha256="2" * 64,
        pixel_count=1,
        mean=value,
        standard_deviation=0.0,
        threshold=value,
    )


def test_submission_contains_matching_binary_thresholded_images(tmp_path: Path) -> None:
    prediction = _prediction(
        tmp_path,
        values=np.array([[1.0, 2.0]], dtype=np.float16),
    )
    manifest = PrivateManifest(images=(prediction.identity,))

    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=(prediction,),
        thresholds={"can": _threshold(1.0)},
    )

    with tarfile.open(archive, "r:gz") as stream:
        continuous_member = stream.extractfile(
            "private_submission/anomaly_images/can/test_private/000_regular.tiff"
        )
        assert continuous_member is not None
        continuous = np.asarray(tifffile.imread(BytesIO(continuous_member.read())))
        assert continuous.dtype == np.float16
        assert continuous.shape == (1, 2)
        member = stream.extractfile(
            "private_submission/anomaly_images_thresholded/can/test_private/000_regular.png"
        )
        assert member is not None
        with Image.open(member) as image:
            assert image.mode == "L"
            assert np.asarray(image).tolist() == [[0, 255]]


def test_submission_contains_every_manifest_image_once(tmp_path: Path) -> None:
    manifest = PrivateManifest(
        images=(
            ("can", "test_private", "000_regular"),
            ("can", "test_private", "001_regular"),
        )
    )
    predictions = (
        _prediction(tmp_path, image_id="000_regular"),
        _prediction(tmp_path, image_id="001_regular"),
    )

    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=predictions,
        thresholds={"can": _threshold(1.0)},
    )

    inspection = inspect_submission(archive)
    expected = {
        "can/test_private/000_regular",
        "can/test_private/001_regular",
    }
    assert set(inspection.continuous_image_ids) == expected
    assert set(inspection.thresholded_image_ids) == expected
    assert len(inspection.continuous_image_ids) == len(set(inspection.continuous_image_ids))
    assert len(inspection.thresholded_image_ids) == len(set(inspection.thresholded_image_ids))


def test_official_utilities_reject_tampered_archive(tmp_path: Path) -> None:
    archive = tmp_path / "utils.tar.gz"
    archive.write_bytes(b"not-the-official-archive")

    try:
        OfficialUtilities.from_archive(archive, expected_sha256="0" * 64)
    except ValueError as error:
        assert "SHA-256" in str(error)
    else:
        raise AssertionError("tampered utility archive was accepted")


def test_verify_archive_requires_exact_manifest(tmp_path: Path) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=(_prediction(tmp_path),),
        thresholds={"can": _threshold(1.0)},
    )

    result = verify_archive(archive, manifest, {"can": _threshold(1.0)})
    assert result.continuous_image_count == 1
    assert result.thresholded_image_count == 1


@pytest.mark.parametrize(
    "thresholds",
    [
        {},
        {"can": _threshold(1.0), "vial": _threshold(1.0, category="vial")},
    ],
)
def test_builder_requires_exact_threshold_categories(
    tmp_path: Path,
    thresholds: dict[str, SubmissionThreshold],
) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    output = tmp_path / "external-output"

    with pytest.raises(ValueError, match="threshold categories"):
        SubmissionBuilder(manifest=manifest).build(
            output_dir=output,
            predictions=(_prediction(tmp_path),),
            thresholds=thresholds,
        )

    assert not (output / "private_submission.tar.gz").exists()


def test_builder_rejects_non_float16_continuous_map(tmp_path: Path) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))

    with pytest.raises(ValueError, match="float16"):
        SubmissionBuilder(manifest=manifest).build(
            output_dir=tmp_path / "external-output",
            predictions=(_prediction(tmp_path, values=np.array([[0.0, 2.0]], dtype=np.float32)),),
            thresholds={"can": _threshold(1.0)},
        )


def test_verify_archive_rejects_missing_thresholded_identity(tmp_path: Path) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    thresholds = {"can": _threshold(1.0)}
    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=(_prediction(tmp_path),),
        thresholds=thresholds,
    )
    tampered = tmp_path / "missing-thresholded.tar.gz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(tampered, "w:gz") as target:
        for member in source.getmembers():
            if "anomaly_images_thresholded" in member.name:
                continue
            target.addfile(member, source.extractfile(member))

    with pytest.raises(ValueError, match="thresholded image identities"):
        verify_archive(tampered, manifest, thresholds)


def _replace_thresholded_png(
    source_archive: Path,
    target_archive: Path,
    values: np.ndarray,
) -> None:
    replacement = BytesIO()
    Image.fromarray(values.astype(np.uint8), mode="L").save(replacement, format="PNG")
    member_name = "private_submission/anomaly_images_thresholded/can/test_private/000_regular.png"
    with (
        tarfile.open(source_archive, "r:gz") as source,
        tarfile.open(target_archive, "w:gz") as target,
    ):
        for member in source.getmembers():
            if member.name == member_name:
                payload = replacement.getvalue()
                member.size = len(payload)
                target.addfile(member, BytesIO(payload))
            else:
                target.addfile(member, source.extractfile(member))


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (np.array([[0], [255]], dtype=np.uint8), "dimensions"),
        (np.array([[1, 255]], dtype=np.uint8), "binary"),
    ],
)
def test_verify_archive_rejects_invalid_thresholded_contract(
    tmp_path: Path,
    values: np.ndarray,
    message: str,
) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    thresholds = {"can": _threshold(1.0)}
    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=(_prediction(tmp_path, values=np.array([[0.0, 2.0]], dtype=np.float16)),),
        thresholds=thresholds,
    )
    tampered = tmp_path / f"invalid-{message}.tar.gz"
    _replace_thresholded_png(archive, tampered, values)

    with pytest.raises(ValueError, match=message):
        verify_archive(tampered, manifest, thresholds)


def test_verify_archive_rejects_duplicate_thresholded_identity(tmp_path: Path) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    thresholds = {"can": _threshold(1.0)}
    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=(_prediction(tmp_path),),
        thresholds=thresholds,
    )
    duplicate = tmp_path / "duplicate-thresholded.tar.gz"
    member_name = "private_submission/anomaly_images_thresholded/can/test_private/000_regular.png"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(duplicate, "w:gz") as target:
        duplicate_member = source.getmember(member_name)
        duplicate_payload = source.extractfile(duplicate_member)
        assert duplicate_payload is not None
        duplicate_bytes = duplicate_payload.read()
        for member in source.getmembers():
            target.addfile(member, source.extractfile(member))
        target.addfile(duplicate_member, BytesIO(duplicate_bytes))

    with pytest.raises(ValueError, match="duplicate thresholded"):
        verify_archive(duplicate, manifest, thresholds)


def test_submission_summary_is_redacted_and_recomputable(tmp_path: Path) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=(_prediction(tmp_path),),
        thresholds={"can": _threshold(1.0)},
    )
    thresholds = {"can": _threshold(1.0)}
    verification = verify_archive(archive, manifest, thresholds)

    summary_path = write_submission_summary(
        tmp_path / "external-output" / "submission_summary.json",
        verification,
        validator_status="PASS",
    )
    text = summary_path.read_text(encoding="utf-8")
    assert "external-output" not in text
    assert '"validator_status": "PASS"' in text
    assert '"schema_version": "2.0.0"' in text
    assert '"continuous_image_count": 1' in text
    assert '"thresholded_image_count": 1' in text
    assert thresholds["can"].identity in text
