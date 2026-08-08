from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

from experiments.submission.build import (
    PrivateManifest,
    SubmissionBuilder,
    SubmissionPrediction,
    inspect_submission,
)
from experiments.submission.official_utils import OfficialUtilities
from experiments.submission.verify import verify_archive, write_submission_summary


def _prediction(tmp_path: Path, *, image_id: str = "000_regular") -> SubmissionPrediction:
    source = tmp_path / f"{image_id}.tiff"
    tifffile.imwrite(source, np.zeros((4, 4), dtype=np.float16))
    return SubmissionPrediction(
        category="can",
        split="test_private",
        image_id=image_id,
        anomaly_map=source,
    )


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
    )

    inspection = inspect_submission(archive)
    assert set(inspection.image_ids) == {
        "can/test_private/000_regular",
        "can/test_private/001_regular",
    }
    assert len(inspection.image_ids) == len(set(inspection.image_ids))


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
    )

    result = verify_archive(archive, manifest)
    assert result.image_count == 1


def test_submission_summary_is_redacted_and_recomputable(tmp_path: Path) -> None:
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))
    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=tmp_path / "external-output",
        predictions=(_prediction(tmp_path),),
    )
    verification = verify_archive(archive, manifest)

    summary_path = write_submission_summary(
        tmp_path / "external-output" / "submission_summary.json",
        verification,
        validator_status="PASS",
    )
    text = summary_path.read_text(encoding="utf-8")
    assert "external-output" not in text
    assert '"validator_status": "PASS"' in text
