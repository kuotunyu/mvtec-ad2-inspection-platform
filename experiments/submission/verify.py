from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from experiments.submission.build import PrivateManifest, inspect_submission


@dataclass(frozen=True, slots=True)
class ArchiveVerification:
    archive: Path
    archive_sha256: str
    image_count: int


def write_submission_summary(
    path: Path,
    verification: ArchiveVerification,
    *,
    validator_status: str,
) -> Path:
    if validator_status not in {"PASS", "PENDING_EXTERNAL_SUBMISSION"}:
        raise ValueError("unsupported validator status")
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "archive_filename": verification.archive.name,
        "archive_sha256": verification.archive_sha256,
        "image_count": verification.image_count,
        "schema_version": "1.0.0",
        "validator_status": validator_status,
    }
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return resolved


def verify_archive(archive: Path, manifest: PrivateManifest) -> ArchiveVerification:
    resolved = archive.expanduser().resolve(strict=True)
    inspection = inspect_submission(resolved)
    expected = {
        "/".join((category, split, image_id)) for category, split, image_id in manifest.images
    }
    actual = set(inspection.image_ids)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"archive image identities differ: missing={missing[:4]} extra={extra[:4]}"
        )
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return ArchiveVerification(
        archive=resolved,
        archive_sha256=digest.hexdigest(),
        image_count=len(actual),
    )
