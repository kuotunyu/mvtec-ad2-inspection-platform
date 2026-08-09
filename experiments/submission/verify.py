from __future__ import annotations

import hashlib
import json
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

from experiments.submission.build import PrivateManifest, inspect_submission
from experiments.submission.thresholds import SubmissionThreshold


@dataclass(frozen=True, slots=True)
class ArchiveVerification:
    archive: Path
    archive_sha256: str
    continuous_image_count: int
    thresholded_image_count: int
    calibration_sha256: dict[str, str]


def write_submission_summary(
    path: Path,
    verification: ArchiveVerification,
    *,
    validator_status: str,
) -> Path:
    if validator_status not in {
        "PASS",
        "LOCAL-PREFLIGHT-NOT-SUBMITTED",
        "PENDING_EXTERNAL_SUBMISSION",
    }:
        raise ValueError("unsupported validator status")
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "archive_filename": verification.archive.name,
        "archive_sha256": verification.archive_sha256,
        "calibration_sha256": verification.calibration_sha256,
        "continuous_image_count": verification.continuous_image_count,
        "schema_version": "2.0.0",
        "thresholded_image_count": verification.thresholded_image_count,
        "validator_status": validator_status,
    }
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return resolved


def _expected_identities(manifest: PrivateManifest) -> set[str]:
    return {"/".join((category, split, image_id)) for category, split, image_id in manifest.images}


def _require_exact_identities(
    *,
    kind: str,
    identities: tuple[str, ...],
    expected: set[str],
) -> None:
    actual = set(identities)
    if len(actual) != len(identities):
        raise ValueError(f"archive contains duplicate {kind} image identities")
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"archive {kind} image identities differ: missing={missing[:4]} extra={extra[:4]}"
        )


def _validate_image_contracts(archive: Path) -> None:
    continuous_shapes: dict[str, tuple[int, int]] = {}
    thresholded_shapes: dict[str, tuple[int, int]] = {}
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            parts = Path(member.name).parts
            if len(parts) != 5 or not member.isfile():
                continue
            payload = stream.extractfile(member)
            if payload is None:
                raise ValueError(f"archive image member cannot be read: {member.name}")
            if parts[1] == "anomaly_images" and Path(member.name).suffix == ".tiff":
                identity = "/".join(parts[2:]).removesuffix(".tiff")
                values = np.asarray(tifffile.imread(BytesIO(payload.read())))
                if values.dtype != np.float16 or values.ndim != 2 or not np.isfinite(values).all():
                    raise ValueError("continuous images must be finite 2D float16 TIFF files")
                continuous_shapes[identity] = values.shape
            elif parts[1] == "anomaly_images_thresholded" and Path(member.name).suffix == ".png":
                identity = "/".join(parts[2:]).removesuffix(".png")
                with Image.open(BytesIO(payload.read())) as image:
                    if image.mode != "L":
                        raise ValueError(
                            "thresholded images must be single-channel mode-L PNG files"
                        )
                    binary = np.asarray(image)
                if not set(np.unique(binary).tolist()).issubset({0, 255}):
                    raise ValueError("thresholded PNG values must be exactly binary 0 or 255")
                thresholded_shapes[identity] = binary.shape
    if continuous_shapes != thresholded_shapes:
        raise ValueError("continuous and thresholded image dimensions differ")


def verify_archive(
    archive: Path,
    manifest: PrivateManifest,
    thresholds: Mapping[str, SubmissionThreshold],
) -> ArchiveVerification:
    resolved = archive.expanduser().resolve(strict=True)
    expected_categories = {category for category, _split, _image_id in manifest.images}
    if set(thresholds) != expected_categories:
        raise ValueError("threshold categories do not match private manifest")
    inspection = inspect_submission(resolved)
    expected = _expected_identities(manifest)
    _require_exact_identities(
        kind="continuous",
        identities=inspection.continuous_image_ids,
        expected=expected,
    )
    _require_exact_identities(
        kind="thresholded",
        identities=inspection.thresholded_image_ids,
        expected=expected,
    )
    _validate_image_contracts(resolved)
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return ArchiveVerification(
        archive=resolved,
        archive_sha256=digest.hexdigest(),
        continuous_image_count=len(inspection.continuous_image_ids),
        thresholded_image_count=len(inspection.thresholded_image_ids),
        calibration_sha256={
            category: threshold.identity for category, threshold in sorted(thresholds.items())
        },
    )
