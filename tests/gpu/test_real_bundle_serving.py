from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from experiments.data.manifest import REQUIRED_CATEGORIES
from scripts.benchmark_serving import (
    summarize_samples,
    validate_serving_report,
    write_serving_evidence,
)
from scripts.gpu_product_smoke import discover_champion_run_ids, run_real_serving_gate


def _identity(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_discovers_seed_42_run_for_each_frozen_category(tmp_path: Path) -> None:
    decisions: list[dict[str, object]] = []
    expected: dict[str, str] = {}
    runs = tmp_path / "runs"
    for category in REQUIRED_CATEGORIES:
        identities = tuple(_identity(f"{category}-{seed}") for seed in (17, 42, 2026))
        expected[category] = identities[1]
        decisions.append(
            {
                "category": category,
                "decision": {"winner": "patchcore"},
                "candidates": [
                    {"family": "patchcore", "run_identities": list(identities)},
                    {"family": "dinomaly", "run_identities": []},
                ],
            }
        )
        for identity, seed in zip(identities, (17, 42, 2026), strict=True):
            run = runs / identity
            run.mkdir(parents=True)
            (run / "spec.json").write_text(
                json.dumps(
                    {
                        "canonical_sha256": identity,
                        "category": category,
                        "model_family": "patchcore",
                        "seed": seed,
                    }
                ),
                encoding="utf-8",
            )
    champions = tmp_path / "champions.json"
    champions.write_text(
        json.dumps(
            {"champions": dict.fromkeys(REQUIRED_CATEGORIES, "patchcore"), "decisions": decisions}
        ),
        encoding="utf-8",
    )

    assert discover_champion_run_ids(champions, runs) == expected


def test_serving_summary_uses_literal_percentiles_and_throughput() -> None:
    summary = summarize_samples([10.0, 20.0, 30.0, 40.0, 50.0])
    assert summary["p50_latency_ms"] == 30.0
    assert summary["p95_latency_ms"] == 48.0
    assert summary["mean_latency_ms"] == 30.0
    assert summary["throughput_images_per_second"] == pytest.approx(1000 / 30)
    lower, upper = summary["mean_latency_95ci_ms"]
    assert lower < summary["mean_latency_ms"] < upper


def test_serving_report_rejects_private_path_or_image_identifier() -> None:
    report = {
        "schema_version": "1.0.0",
        "status": "passed",
        "code_sha": "1" * 40,
        "categories": {category: {"family": "patchcore"} for category in REQUIRED_CATEGORIES},
    }
    assert validate_serving_report(report) == ()
    report["source"] = r"C:\Users\operator\private-image.png"
    assert "private_path_or_image" in validate_serving_report(report)


def test_serving_writer_binds_report_bytes_to_manifest(tmp_path: Path) -> None:
    report = {
        "schema_version": "1.0.0",
        "status": "passed",
        "code_sha": "1" * 40,
        "categories": {category: {"family": "patchcore"} for category in REQUIRED_CATEGORIES},
    }
    output = tmp_path / "evidence" / "serving-benchmark.json"
    write_serving_evidence(output, report)
    manifest = json.loads((output.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"][output.name] == hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.gpu
@pytest.mark.dataset
def test_real_champions_serve_in_clean_category_processes() -> None:
    if os.environ.get("RUN_REAL_SERVING_GATE") != "1":
        pytest.skip("set RUN_REAL_SERVING_GATE=1 after acquiring the formal GPU lease")
    results = run_real_serving_gate(
        evidence_root=Path(os.environ["MVTECAD2_EVIDENCE_ROOT"]),
        runs_root=Path(os.environ["MVTECAD2_RUNS_ROOT"]),
        data_root=Path(os.environ["MVTECAD2_DATA_ROOT"]),
        registry_root=Path(os.environ["INSPECTION_MODEL_ROOT"]),
        code_sha=os.environ["SOURCE_REVISION"],
    )
    assert set(results) == set(REQUIRED_CATEGORIES)
    assert all(item["status"] == "passed" for item in results.values())
