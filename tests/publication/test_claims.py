from __future__ import annotations

from pathlib import Path

from scripts.verify_claims import extract_claims, verify_claims


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
