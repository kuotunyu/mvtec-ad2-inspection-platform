from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.capture_study_environment import (
    build_environment,
    build_sidecar,
    candidate_run_identities,
    training_peaks,
    write_sidecar,
)

_CAN_RUN = "b" * 64
_WALLPLUGS_RUN = "c" * 64


def _gpu() -> tuple[str, str, int]:
    return "NVIDIA A100-SXM4-80GB", "580.82.07", 81920


def _versions() -> dict[str, str]:
    return {
        "anomalib": "2.5.0",
        "cuda_runtime": "13.0",
        "platform": "Linux",
        "python": "3.12.13",
        "torch": "2.13.0+cu130",
    }


def _report(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "canonical_sha256": "a" * 64,
        "comparisons": [
            {"category": "can", "candidate_run_identity": _CAN_RUN},
            {"category": "wallplugs", "candidate_run_identity": _WALLPLUGS_RUN},
        ],
        "failures": [],
        "scope": "test_public-only",
        "study": "patchcore-512-vs-768-can-wallplugs-seed42",
        "submitted": False,
        "verdict": "PROMISING",
    }
    payload.update(overrides)
    return payload


def _runs_root(tmp_path: Path, peaks: dict[str, float]) -> Path:
    identities = {"can": _CAN_RUN, "wallplugs": _WALLPLUGS_RUN}
    for category, peak in peaks.items():
        run_dir = tmp_path / identities[category]
        run_dir.mkdir(parents=True)
        (run_dir / "record.json").write_text(json.dumps({"peak_vram_mib": peak}), encoding="utf-8")
    return tmp_path


def test_environment_block_uses_serving_benchmark_field_names() -> None:
    environment = build_environment(gpu=_gpu, versions=_versions)

    assert set(environment) == {
        "anomalib",
        "cuda_runtime",
        "gpu_driver",
        "gpu_memory_mib",
        "gpu_name",
        "platform",
        "python",
        "torch",
    }
    assert environment["gpu_memory_mib"] == 81920
    assert environment["gpu_name"] == "NVIDIA A100-SXM4-80GB"


def test_environment_block_rejects_an_incomplete_probe() -> None:
    with pytest.raises(ValueError, match="incomplete identity"):
        build_environment(gpu=lambda: ("", "580.82.07", 81920), versions=_versions)


def test_sidecar_binds_report_identity_and_records_training_peaks(tmp_path: Path) -> None:
    runs_root = _runs_root(tmp_path, {"can": 46600.0, "wallplugs": 33200.0})

    payload = build_sidecar(
        report=_report(),
        runs_root=runs_root,
        environment=build_environment(gpu=_gpu, versions=_versions),
    )

    assert payload["study_report_sha256"] == "a" * 64
    assert payload["schema_version"] == "1.0.0"
    assert payload["evaluation_scope"] == "test_public-only"
    assert payload["submitted"] is False
    assert payload["verdict"] == "PROMISING"
    assert payload["training_peak_vram_mib"] == {"can": 46600.0, "wallplugs": 33200.0}


def test_sidecar_reads_run_identities_from_failures(tmp_path: Path) -> None:
    report = _report(
        comparisons=[],
        failures=[
            {"category": "can", "candidate_run_identity": _CAN_RUN},
            {"category": "wallplugs", "candidate_run_identity": _WALLPLUGS_RUN},
        ],
        verdict="RESOURCE_LIMIT_EXCEEDED",
    )
    runs_root = _runs_root(tmp_path, {"can": 81000.0, "wallplugs": 33200.0})

    payload = build_sidecar(
        report=report,
        runs_root=runs_root,
        environment=build_environment(gpu=_gpu, versions=_versions),
    )

    assert payload["verdict"] == "RESOURCE_LIMIT_EXCEEDED"
    assert sorted(payload["training_peak_vram_mib"]) == ["can", "wallplugs"]


def test_candidate_run_identities_requires_at_least_one_outcome() -> None:
    with pytest.raises(ValueError, match="no candidate run identity"):
        candidate_run_identities(_report(comparisons=[], failures=[]))


def test_candidate_run_identities_rejects_a_duplicated_category() -> None:
    report = _report(failures=[{"category": "can", "candidate_run_identity": _WALLPLUGS_RUN}])

    with pytest.raises(ValueError, match="more than once"):
        candidate_run_identities(report)


def test_training_peaks_rejects_a_missing_or_zero_peak(tmp_path: Path) -> None:
    runs_root = _runs_root(tmp_path, {"can": 46600.0})
    (runs_root / _WALLPLUGS_RUN).mkdir(parents=True)
    (runs_root / _WALLPLUGS_RUN / "record.json").write_text(
        json.dumps({"peak_vram_mib": 0}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="positive peak_vram_mib"):
        training_peaks(runs_root, {"can": _CAN_RUN, "wallplugs": _WALLPLUGS_RUN})


def test_sidecar_rejects_a_submitted_report(tmp_path: Path) -> None:
    runs_root = _runs_root(tmp_path, {"can": 46600.0, "wallplugs": 33200.0})

    with pytest.raises(ValueError, match="unsubmitted public-only"):
        build_sidecar(
            report=_report(submitted=True),
            runs_root=runs_root,
            environment=build_environment(gpu=_gpu, versions=_versions),
        )


def test_sidecar_refuses_a_private_path_fragment(tmp_path: Path) -> None:
    runs_root = _runs_root(tmp_path, {"can": 46600.0, "wallplugs": 33200.0})
    poisoned = build_environment(
        gpu=lambda: ("/home/operator/gpu", "580.82.07", 81920),
        versions=_versions,
    )

    with pytest.raises(ValueError, match="private path fragment"):
        build_sidecar(report=_report(), runs_root=runs_root, environment=poisoned)


def test_write_sidecar_is_idempotent_and_refuses_conflicting_content(tmp_path: Path) -> None:
    runs_root = _runs_root(tmp_path / "runs", {"can": 46600.0, "wallplugs": 33200.0})
    payload = build_sidecar(
        report=_report(),
        runs_root=runs_root,
        environment=build_environment(gpu=_gpu, versions=_versions),
    )
    destination = tmp_path / "out" / "environment.json"

    first = write_sidecar(destination, payload)
    second = write_sidecar(destination, payload)

    assert first == second
    assert first.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(first.read_text(encoding="utf-8")) == payload

    with pytest.raises(ValueError, match="differs"):
        write_sidecar(destination, {**payload, "verdict": "MIXED"})
