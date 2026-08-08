from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path


class SubmissionValidationError(RuntimeError):
    """Raised when the pinned official validator rejects a bundle."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class OfficialUtilities:
    """Checksum-pinned adapter for the official local submission validator."""

    root: Path
    archive: Path
    validator: Path
    archive_sha256: str

    @classmethod
    def from_archive(
        cls,
        archive: Path,
        *,
        expected_sha256: str,
        extracted_root: Path | None = None,
    ) -> OfficialUtilities:
        archive = archive.expanduser().resolve(strict=True)
        actual = sha256_file(archive)
        if actual != expected_sha256:
            raise ValueError(
                "official utility archive SHA-256 mismatch: "
                f"expected={expected_sha256} actual={actual}"
            )
        destination = (
            extracted_root.expanduser().resolve()
            if extracted_root is not None
            else archive.with_suffix("")
        )
        validator = (
            destination
            / "MVTecAD2_public_code_utils"
            / "check_and_prepare_data_for_upload.py"
        )
        if not validator.exists():
            destination.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive, "r:gz") as stream:
                stream.extractall(destination)
        validator = validator.resolve(strict=True)
        return cls(
            root=validator.parent,
            archive=archive,
            validator=validator,
            archive_sha256=actual,
        )

    @classmethod
    def from_directory(cls, root: Path, *, archive_sha256: str) -> OfficialUtilities:
        resolved = root.expanduser().resolve(strict=True)
        validator = (resolved / "check_and_prepare_data_for_upload.py").resolve(strict=True)
        return cls(
            root=resolved,
            archive=resolved,
            validator=validator,
            archive_sha256=archive_sha256,
        )

    def validate(self, submission_dir: Path) -> None:
        submission = submission_dir.expanduser().resolve(strict=True)
        completed = subprocess.run(
            [sys.executable, str(self.validator), str(submission)],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        generated = self.root / f"{submission.name}.tar.gz"
        generated.unlink(missing_ok=True)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise SubmissionValidationError(
                f"official validator rejected {submission}: {detail[-2000:]}"
            )
