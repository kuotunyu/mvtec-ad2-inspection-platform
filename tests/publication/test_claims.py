from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.data.manifest import REQUIRED_CATEGORIES
from scripts.verify_claims import extract_claims, verify_claims, verify_serving_evidence


def test_every_declared_numeric_claim_resolves_to_sanitized_evidence() -> None:
    docs = [Path("README.md"), Path("docs/CASE_STUDY.md"), Path("docs/MODEL_CARD.md")]
    claims = extract_claims(docs)
    assert len(claims) >= 2
    report = verify_claims(claims, Path("."))
    assert report.ok, report.errors


def test_metric_like_claims_are_evidence_annotated() -> None:
    for path in (Path("README.md"), Path("docs/CASE_STUDY.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if any(
                unit in line for unit in (" formal public runs", " category-specific champions")
            ):
                assert "<!-- claim:" in line


def test_serving_evidence_is_bound_to_a_sanitized_manifest_hash(tmp_path: Path) -> None:
    evidence = tmp_path / "docs/assets/evidence"
    evidence.mkdir(parents=True)
    serving = evidence / "serving-benchmark.json"
    serving.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "status": "passed",
                "code_sha": "1" * 40,
                "categories": {
                    category: {"family": "patchcore"} for category in REQUIRED_CATEGORIES
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = evidence / "manifest.json"
    manifest.write_text(
        json.dumps({"files": {"serving-benchmark.json": "0" * 64}}), encoding="utf-8"
    )
    assert "serving_evidence_hash" in verify_serving_evidence(tmp_path)
    manifest.write_text(
        json.dumps(
            {"files": {"serving-benchmark.json": hashlib.sha256(serving.read_bytes()).hexdigest()}}
        ),
        encoding="utf-8",
    )
    assert verify_serving_evidence(tmp_path) == ()
