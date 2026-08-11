from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.data.manifest import REQUIRED_CATEGORIES
from scripts.benchmark_serving import (
    summarize_samples,
    validate_serving_report,
    write_serving_evidence,
)
from scripts.gpu_product_smoke import (
    canonical_mapping_hash,
    discover_champion_run_ids,
    record_matches_spec,
    run_real_serving_gate,
    validate_workstation_detail,
)


def test_real_serving_children_receive_parent_gpu_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    image = tmp_path / "image.png"
    image.write_bytes(b"public-test-input")
    gpu_lock = tmp_path / "gpu.lock"
    bundle_identity = "b" * 64
    commands: list[list[str]] = []

    class FakeHandle:
        def heartbeat(self) -> None:
            return None

    class FakeAcquisition:
        def __enter__(self) -> FakeHandle:
            return FakeHandle()

        def __exit__(self, *_args: object) -> None:
            return None

    class FakeLease:
        def acquire(self, _purpose: str) -> FakeAcquisition:
            return FakeAcquisition()

    monkeypatch.setattr("scripts.gpu_product_smoke.GpuLease", lambda *_args, **_kwargs: FakeLease())
    monkeypatch.setattr(
        "scripts.gpu_product_smoke.prepare_real_registry",
        lambda *_args, **_kwargs: {
            "categories": {
                category: {"bundle_identity": bundle_identity} for category in REQUIRED_CATEGORIES
            }
        },
    )
    monkeypatch.setattr("scripts.gpu_product_smoke._input_for_category", lambda *_args: image)

    def completed_child(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        output = Path(command[command.index("--output") + 1])
        output.write_text(
            json.dumps({"status": "passed", "bundle_identity": bundle_identity}),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("scripts.gpu_product_smoke.subprocess.run", completed_child)

    results = run_real_serving_gate(
        evidence_root=tmp_path,
        runs_root=tmp_path,
        data_root=data,
        registry_root=tmp_path / "registry",
        code_sha="a" * 40,
        gpu_lock=gpu_lock,
    )

    assert set(results) == set(REQUIRED_CATEGORIES)
    assert len(commands) == len(REQUIRED_CATEGORIES)
    assert all(command[command.index("--gpu-lock") + 1] == str(gpu_lock) for command in commands)


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


def test_completed_record_embeds_spec_without_computed_identity() -> None:
    spec = {"canonical_sha256": "a" * 64, "category": "can", "seed": 42}
    record = {"spec": {"category": "can", "seed": 42}}
    assert record_matches_spec(record, spec)


def test_registry_index_hash_is_canonical_and_ignores_stored_identity() -> None:
    left = {"z": 2, "a": {"value": 1}}
    right = {"a": {"value": 1}, "z": 2, "canonical_sha256": "f" * 64}
    assert canonical_mapping_hash(left) == canonical_mapping_hash(right)


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
    separator = chr(92)
    report["source"] = separator.join(("C:", "Users", "operator", "private-image.png"))
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


def test_real_serving_gate_requires_distinct_workstation_spatial_evidence() -> None:
    detail = {
        "status": "COMPLETED",
        "model_bundle_id": "c" * 64,
        "images": [
            {
                "source_url": "/api/v1/artifacts/image/source",
                "anomaly_map_url": "/api/v1/artifacts/image/anomaly-map",
                "overlay_url": "/api/v1/artifacts/image/overlay",
                "anomaly_map_sha256": "a" * 64,
                "overlay_sha256": "b" * 64,
                "anomaly_score": 0.5,
                "error": None,
            }
        ],
    }
    assert validate_workstation_detail(detail) == ()
    detail["images"][0]["overlay_url"] = detail["images"][0]["source_url"]
    assert "spatial_artifact_routes" in validate_workstation_detail(detail)


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
        gpu_lock=Path(os.environ["MVTECAD2_GPU_LOCK"]),
    )
    assert set(results) == set(REQUIRED_CATEGORIES)
    assert all(item["status"] == "passed" for item in results.values())
