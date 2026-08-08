"""Fail-closed verification for clean exports and experiment handoff evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class CleanExportError(ValueError):
    """Raised when an export contains data, secrets, or workstation paths."""


@dataclass(frozen=True)
class CleanExportResult:
    status: str
    file_count: int
    archive_sha256: str


_FORBIDDEN_PARTS = {
    ".env",
    "checkpoints",
    "data",
    "datasets",
    "predictions",
    "runs",
    "weights",
}
_ABSOLUTE_WINDOWS = re.compile(r"^[A-Za-z]:[/\\]")


def _archive_sha256(archive: Path) -> str:
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_clean_export(archive: Path) -> CleanExportResult:
    """Verify a source-only tar archive and reject private/runtime material."""

    archive = archive.resolve()
    if not archive.is_file():
        raise CleanExportError(f"archive does not exist: {archive}")
    members: list[str] = []
    with tarfile.open(archive, "r:*") as handle:
        for member in handle.getmembers():
            name = member.name.replace("\\", "/")
            path = PurePosixPath(name)
            if path.is_absolute() or _ABSOLUTE_WINDOWS.match(name) or ".." in path.parts:
                raise CleanExportError(f"unsafe archive path: {name}")
            lowered = {part.lower() for part in path.parts}
            has_private = any(part.lower().startswith("private") for part in path.parts)
            if lowered & _FORBIDDEN_PARTS or has_private:
                raise CleanExportError(f"forbidden export path: {name}")
            members.append(name)
    return CleanExportResult("PASS", len(members), _archive_sha256(archive))


def verify_experiments(repo_root: Path, submission_summary: Path | None = None) -> str:
    """Verify committed evidence and report a fail-closed handoff status."""

    required = [
        repo_root / "reports" / "public_benchmark.json",
        repo_root / "reports" / "champions.json",
        repo_root / "reports" / "contenders.json",
        repo_root / "reports" / "schemas" / "benchmark.schema.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise CleanExportError("missing required evidence: " + ", ".join(missing))
    for path in required:
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
    if submission_summary is None or not submission_summary.is_file():
        return "PENDING EXTERNAL SUBMISSION"
    summary = json.loads(submission_summary.read_text(encoding="utf-8"))
    if summary.get("validator_status") != "PASS":
        return "PENDING EXTERNAL SUBMISSION"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--submission-summary", type=Path)
    args = parser.parse_args()
    try:
        status = verify_experiments(args.repo_root.resolve(), args.submission_summary)
    except (CleanExportError, json.JSONDecodeError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
