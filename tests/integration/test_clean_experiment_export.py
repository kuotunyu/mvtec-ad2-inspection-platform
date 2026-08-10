from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from scripts.verify_experiments import CleanExportError, verify_clean_export, verify_experiments


def _write_foundation_evidence(repo_root: Path) -> None:
    reports = repo_root / "reports"
    (reports / "schemas").mkdir(parents=True)
    for path in (
        reports / "public_benchmark.json",
        reports / "champions.json",
        reports / "contenders.json",
        reports / "schemas" / "benchmark.schema.json",
    ):
        path.write_text("{}\n", encoding="utf-8")


def _write_official_evidence(
    repo_root: Path,
    *,
    status: str = "DONE",
    verdict: str = "PRIVATE-NO-GO",
    manifest_hash: str | None = None,
) -> None:
    evidence = repo_root / "docs" / "assets" / "evidence"
    evidence.mkdir(parents=True)
    official = evidence / "official-private-result.json"
    official.write_text(
        json.dumps({"status": status, "verdict": verdict}) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(official.read_bytes()).hexdigest()
    (evidence / "manifest.json").write_text(
        json.dumps({"files": {"official-private-result.json": manifest_hash or digest}}) + "\n",
        encoding="utf-8",
    )


def test_clean_export_rejects_private_and_absolute_paths(tmp_path: Path) -> None:
    archive = tmp_path / "repo.tar.gz"
    payload = tmp_path / "payload"
    (payload / "predictions").mkdir(parents=True)
    (payload / "predictions" / "private.tiff").write_bytes(b"private")
    (payload / "README.md").write_text("ok\n", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(payload / "README.md", arcname="README.md")
        handle.add(payload / "predictions" / "private.tiff", arcname="predictions/private.tiff")

    with pytest.raises(CleanExportError, match=r"predictions/private\.tiff"):
        verify_clean_export(archive)


def test_clean_export_accepts_declared_source_files(tmp_path: Path) -> None:
    archive = tmp_path / "repo.tar.gz"
    source = tmp_path / "source.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(source, arcname="src/source.py")

    result = verify_clean_export(archive)
    assert result.status == "PASS"
    assert result.file_count == 1


def test_experiment_verifier_reports_pending_without_submission_evidence(
    tmp_path: Path,
) -> None:
    _write_foundation_evidence(tmp_path)

    assert verify_experiments(tmp_path) == "PENDING EXTERNAL SUBMISSION"


def test_experiment_verifier_accepts_passing_external_summary(tmp_path: Path) -> None:
    _write_foundation_evidence(tmp_path)
    summary = tmp_path / "submission-summary.json"
    summary.write_text('{"validator_status":"PASS"}\n', encoding="utf-8")

    assert verify_experiments(tmp_path, summary) == "PASS"


def test_experiment_verifier_accepts_manifested_complete_official_result(
    tmp_path: Path,
) -> None:
    _write_foundation_evidence(tmp_path)
    _write_official_evidence(tmp_path)

    assert verify_experiments(tmp_path) == "PASS"


@pytest.mark.parametrize(
    ("status", "verdict", "manifest_hash", "message"),
    [
        ("PENDING", "PRIVATE-NO-GO", None, "official result is incomplete"),
        ("DONE", "UNKNOWN", None, "unknown official verdict"),
        ("DONE", "PRIVATE-NO-GO", "0" * 64, "official result hash mismatch"),
    ],
)
def test_experiment_verifier_rejects_invalid_committed_official_result(
    tmp_path: Path,
    status: str,
    verdict: str,
    manifest_hash: str | None,
    message: str,
) -> None:
    _write_foundation_evidence(tmp_path)
    _write_official_evidence(
        tmp_path,
        status=status,
        verdict=verdict,
        manifest_hash=manifest_hash,
    )

    with pytest.raises(CleanExportError, match=message):
        verify_experiments(tmp_path)


def test_experiment_verifier_rejects_unmanifested_official_result(
    tmp_path: Path,
) -> None:
    _write_foundation_evidence(tmp_path)
    _write_official_evidence(tmp_path)
    (tmp_path / "docs" / "assets" / "evidence" / "manifest.json").unlink()

    with pytest.raises(CleanExportError, match="missing official evidence manifest"):
        verify_experiments(tmp_path)
