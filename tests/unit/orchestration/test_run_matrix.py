from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.orchestration.queue import expand_stage
from experiments.run_matrix import (
    CONFIG_ROOT,
    _freeze_queue,
    _resolve_imagenette_root,
    build_stage,
    main,
)
from inspection_platform.contracts import DatasetManifest


def write_manifest(path: Path) -> None:
    manifest = DatasetManifest(
        archive_url="https://example.invalid/mvtec-ad-2.tar.gz",
        archive_size=1,
        archive_sha256="a" * 64,
        category_counts={"can": {"train/good": 1}},
        extensions=(".png",),
        files=(),
    )
    payload = manifest.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = manifest.identity
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_screening_dry_run_reports_24_stable_identities_without_gpu(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_root = tmp_path / "dataset"
    data_root.mkdir()
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest)

    assert (
        main(
            [
                "--stage",
                "screening",
                "--data-root",
                str(data_root),
                "--runs-root",
                str(tmp_path / "runs"),
                "--dataset-manifest",
                str(manifest),
                "--dry-run",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "screening"
    assert payload["count"] == 24
    assert len(set(payload["identities"])) == 24
    assert not (tmp_path / "runs").exists()


def test_frozen_queue_is_idempotent_and_never_overwritten(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("canonical_sha256")
    manifest = DatasetManifest.model_validate(payload)
    stage = build_stage(
        name="screening",
        config_root=CONFIG_ROOT,
        manifest=manifest,
        contenders_path=None,
    )
    queue = expand_stage(stage)
    root = tmp_path / "runs"
    root.mkdir()

    first = _freeze_queue(root, stage=stage, queue=queue, code_revision="a" * 40)
    second = _freeze_queue(root, stage=stage, queue=queue, code_revision="a" * 40)

    assert first == second
    original = first.read_bytes()
    with pytest.raises(ValueError, match="frozen queue"):
        _freeze_queue(root, stage=stage, queue=queue, code_revision="b" * 40)
    assert first.read_bytes() == original


def test_formal_worker_resolves_imagenette_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    imagenette = tmp_path / "imagenette"
    imagenette.mkdir()
    monkeypatch.setenv("MVTECAD2_IMAGENETTE_ROOT", str(imagenette))

    assert _resolve_imagenette_root(None) == imagenette.resolve()
