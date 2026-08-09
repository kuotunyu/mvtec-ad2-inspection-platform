from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_demo_bundle import build_demo_bundle
from scripts.verify_contract_chain import verify_contract_chain


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("dataset_hash", "dataset_hash"),
        ("metric_contract", "metric_contract"),
        ("preprocess_hash", "preprocess_hash"),
        ("threshold", "threshold"),
        ("weight_hash", "weight_hash"),
    ],
)
def test_contract_chain_rejects_identity_drift(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    registry = tmp_path / "registry"
    build_demo_bundle(registry)
    chain_path = registry / "contract-chain.json"
    payload = json.loads(chain_path.read_text(encoding="utf-8"))
    if mutation == "dataset_hash":
        payload["dataset_manifest_sha256"] = "f" * 64
    elif mutation == "metric_contract":
        payload["metric_contract_version"] = "9.0.0"
    elif mutation == "preprocess_hash":
        payload["preprocessing_sha256"] = "f" * 64
    elif mutation == "threshold":
        payload["threshold_contract"] = "changed"
    else:
        first = sorted(payload["bundle_manifest_sha256"])[0]
        payload["bundle_manifest_sha256"][first] = "f" * 64
    chain_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = verify_contract_chain(Path("reports"), registry)
    assert not report.ok
    assert expected in report.error_codes


def test_valid_demo_chain_is_complete_and_bidirectional(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    manifests = build_demo_bundle(registry)
    report = verify_contract_chain(Path("reports"), registry)
    assert report.ok
    assert len(manifests) == 8
    assert report.checked_categories == 8
