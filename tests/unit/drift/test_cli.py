from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event, Thread

import pytest
from pytest import MonkeyPatch

from experiments.drift.cli import main
from experiments.models.base import ArtifactFile, PredictionArtifact, PredictionSplit
from experiments.train import write_contract
from inspection_platform.contracts import PredictionRecord
from inspection_platform.contracts.dataset import MVTecAD2Category


def _artifact(
    category: MVTecAD2Category, split: PredictionSplit, scores: tuple[float, ...]
) -> PredictionArtifact:
    records: list[PredictionRecord] = []
    maps: list[ArtifactFile] = []
    for index, score in enumerate(scores):
        map_digest = f"{index + 1:064x}"
        maps.append(ArtifactFile(path=Path(f"map-{index}.npy"), sha256=map_digest, size=1))
        records.append(
            PredictionRecord(
                input_id=f"input-{index}",
                input_sha256=f"{index + 101:064x}",
                category=category,
                anomaly_score=score,
                anomaly_map_sha256=map_digest,
                model_bundle_id=f"champion-{category}",
            )
        )
    return PredictionArtifact(
        family="patchcore",
        category=category,
        split=split,
        config_sha256="a" * 64,
        records=tuple(records),
        anomaly_maps=tuple(maps),
    )


def test_cli_writes_deterministic_versioned_report(tmp_path: Path) -> None:
    baseline_can = write_contract(
        tmp_path / "baseline-can.json", _artifact("can", "test_public", (0.1, 0.2, 0.3))
    )
    baseline_vial = write_contract(
        tmp_path / "baseline-vial.json", _artifact("vial", "test_public", (0.2, 0.3, 0.4))
    )
    current_can = write_contract(
        tmp_path / "current-can.json", _artifact("can", "validation", (0.2, 0.3, 0.4))
    )
    current_vial = write_contract(
        tmp_path / "current-vial.json", _artifact("vial", "validation", (0.3, 0.4, 0.5))
    )
    first_output = tmp_path / "first-report.json"
    second_output = tmp_path / "second-report.json"

    assert (
        main(
            [
                "--baseline-artifact",
                str(baseline_vial),
                str(baseline_can),
                "--current-artifact",
                str(current_can),
                str(current_vial),
                "--baseline-description",
                "public baseline",
                "--current-description",
                "sanitized comparison",
                "--bins",
                "3",
                "--output",
                str(first_output),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--baseline-artifact",
                str(baseline_can),
                str(baseline_vial),
                "--current-artifact",
                str(current_vial),
                str(current_can),
                "--baseline-description",
                "public baseline",
                "--current-description",
                "sanitized comparison",
                "--bins",
                "3",
                "--output",
                str(second_output),
            ]
        )
        == 0
    )

    assert first_output.read_bytes() == second_output.read_bytes()
    assert first_output.read_bytes().endswith(b"\n")
    payload = json.loads(first_output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert [item["category"] for item in payload["comparisons"]] == ["can", "vial"]


def test_cli_refuses_to_overwrite_existing_report(tmp_path: Path) -> None:
    baseline = write_contract(
        tmp_path / "baseline.json", _artifact("can", "test_public", (0.1, 0.2))
    )
    current = write_contract(tmp_path / "current.json", _artifact("can", "validation", (0.1, 0.2)))
    output = tmp_path / "report.json"
    arguments = [
        "--baseline-artifact",
        str(baseline),
        "--current-artifact",
        str(current),
        "--baseline-description",
        "baseline",
        "--current-description",
        "current",
        "--output",
        str(output),
    ]

    assert main(arguments) == 0
    with pytest.raises(FileExistsError, match="already exists"):
        main(arguments)


def test_cli_preserves_destination_created_during_atomic_publish(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    baseline = write_contract(
        tmp_path / "baseline.json", _artifact("can", "test_public", (0.1, 0.2))
    )
    current = write_contract(tmp_path / "current.json", _artifact("can", "validation", (0.1, 0.2)))
    output = tmp_path / "report.json"
    publish_ready = Event()
    release_publish = Event()
    real_fsync = os.fsync

    def pause_after_sync(file_descriptor: int) -> None:
        real_fsync(file_descriptor)
        publish_ready.set()
        assert release_publish.wait(2)

    monkeypatch.setattr("experiments.train.os.fsync", pause_after_sync)
    errors: list[BaseException] = []

    def run_cli() -> None:
        try:
            main(
                [
                    "--baseline-artifact",
                    str(baseline),
                    "--current-artifact",
                    str(current),
                    "--baseline-description",
                    "baseline",
                    "--current-description",
                    "current",
                    "--output",
                    str(output),
                ]
            )
        except BaseException as error:
            errors.append(error)

    thread = Thread(target=run_cli)
    thread.start()
    assert publish_ready.wait(2)
    output.write_text("competing writer\n", encoding="utf-8")
    release_publish.set()
    thread.join(2)

    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], FileExistsError)
    assert output.read_text(encoding="utf-8") == "competing writer\n"
    assert not output.with_suffix(".json.tmp").exists()
