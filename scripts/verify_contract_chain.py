from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from inspection_platform.registry.repository import BundleIntegrityError, ModelRegistry
from scripts.build_demo_bundle import PREPROCESSING_SHA256, THRESHOLD_CONTRACT


@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    checked_categories: int
    error_codes: tuple[str, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_contract_chain(evidence_root: Path, registry_root: Path) -> VerificationReport:
    """Verify the frozen evidence-to-demo-registry identity chain in both directions."""
    errors: set[str] = set()
    try:
        champions = json.loads((evidence_root / "champions.json").read_text(encoding="utf-8"))
        chain = json.loads((registry_root / "contract-chain.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError):
        return VerificationReport(False, 0, ("chain_format",))

    categories = set(champions.get("champions", {}))
    manifest_hashes = chain.get("bundle_manifest_sha256", {})
    if chain.get("dataset_manifest_sha256") != champions.get("dataset_manifest_sha256"):
        errors.add("dataset_hash")
    if chain.get("metric_contract_version") != "1.0.0":
        errors.add("metric_contract")
    if chain.get("preprocessing_sha256") != PREPROCESSING_SHA256:
        errors.add("preprocess_hash")
    if chain.get("threshold_contract") != THRESHOLD_CONTRACT:
        errors.add("threshold")
    if set(manifest_hashes) != categories:
        errors.add("weight_hash")

    checked = 0
    registry = ModelRegistry(registry_root)
    for category in sorted(categories):
        manifest_path = registry_root / "categories" / category / "manifest.json"
        if not manifest_path.is_file() or manifest_hashes.get(category) != _sha256(manifest_path):
            errors.add("weight_hash")
            continue
        try:
            manifest = registry.register(manifest_path)
        except (BundleIntegrityError, OSError, json.JSONDecodeError):
            errors.add("weight_hash")
            continue
        checked += 1
        if manifest.category != category or manifest.runtime_kind != "mock":
            errors.add("weight_hash")
        if manifest.preprocessing_sha256 != chain.get("preprocessing_sha256"):
            errors.add("preprocess_hash")
        if manifest.threshold != 0.5:
            errors.add("threshold")

    return VerificationReport(not errors, checked, tuple(sorted(errors)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=Path("reports"))
    parser.add_argument("--registry-root", required=True, type=Path)
    args = parser.parse_args()
    report = verify_contract_chain(args.evidence_root, args.registry_root)
    print(
        json.dumps(
            {
                "ok": report.ok,
                "checked_categories": report.checked_categories,
                "error_codes": report.error_codes,
            }
        )
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
