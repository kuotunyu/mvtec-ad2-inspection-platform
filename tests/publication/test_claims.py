from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.data.manifest import REQUIRED_CATEGORIES
from scripts.verify_claims import extract_claims, verify_claims, verify_serving_evidence

CATEGORIES = {
    "can": 6.63,
    "fabric": 9.41,
    "fruit_jelly": 39.73,
    "rice": 17.02,
    "sheet_metal": 17.76,
    "vial": 70.23,
    "wallplugs": 26.02,
    "walnuts": 63.14,
}


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


def test_official_private_evidence_is_complete_and_manifest_bound(tmp_path: Path) -> None:
    evidence = tmp_path / "docs/assets/evidence"
    evidence.mkdir(parents=True)
    official = evidence / "official-private-result.json"
    zeroes = dict.fromkeys(CATEGORIES, 0.0)
    payload = {
        "schema_version": "1.0.0",
        "benchmark": "MVTec AD 2",
        "method_name": "MVTec AD 2 Industrial Inspection Platform",
        "server_date": "2026-08-09",
        "status": "DONE",
        "verdict": "PRIVATE-NO-GO",
        "submission_archive_sha256": "2" * 64,
        "submission_id_sha256": "3" * 64,
        "archive_inventory": {"anomaly_map_tiff": 4090, "thresholded_png": 0},
        "thresholded_metrics_available": False,
        "metrics": {
            "private": {
                "auc_pro_0_05": {"average": 31.24, "categories": CATEGORIES},
                "class_f1": {"average": 0.0, "categories": zeroes},
                "seg_f1": {"average": 0.0, "categories": zeroes},
            },
            "private_mixed": {
                "auc_pro_0_05": {
                    "average": 29.81,
                    "categories": {
                        "can": 6.31,
                        "fabric": 11.03,
                        "fruit_jelly": 39.16,
                        "rice": 15.57,
                        "sheet_metal": 16.0,
                        "vial": 67.44,
                        "wallplugs": 23.52,
                        "walnuts": 59.41,
                    },
                },
                "class_f1": {"average": 0.0, "categories": zeroes},
                "seg_f1": {"average": 0.0, "categories": zeroes},
            },
        },
        "runtime_ms": None,
        "memory_mb": None,
        "limitations": ["No second submission was performed."],
    }
    official.write_text(json.dumps(payload), encoding="utf-8")
    manifest = evidence / "manifest.json"
    manifest.write_text(
        json.dumps({"files": {"official-private-result.json": "0" * 64}}), encoding="utf-8"
    )
    report = verify_claims((), tmp_path)
    assert "official_private_evidence_hash" in report.errors

    manifest.write_text(
        json.dumps(
            {
                "files": {
                    "official-private-result.json": hashlib.sha256(
                        official.read_bytes()
                    ).hexdigest()
                }
            }
        ),
        encoding="utf-8",
    )
    assert verify_claims((), tmp_path).ok
