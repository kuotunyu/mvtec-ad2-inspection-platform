from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from experiments.models.base import (
    ExportContext,
    FitContext,
    ModelConfig,
    PredictContext,
    load_model_config,
)
from experiments.models.factory import create_adapter
from inspection_platform.contracts import DatasetFile, DatasetManifest, sha256_file

CONFIG_ROOT = Path("experiments/configs/models")


def smoke_config(family: str) -> ModelConfig:
    config = load_model_config(CONFIG_ROOT / f"{family}.yaml")
    payload = config.model_dump(mode="python", exclude_computed_fields=True)
    size = {"patchcore": 64, "efficient_ad": 256, "dinomaly": 112}[family]
    payload["input_size"] = (size, size)
    payload["batch_size"] = 1
    payload["oom_fallback_batch_size"] = None
    payload["trainer_limits"] = {"max_epochs": 1, "max_steps": 1}
    preprocessing = dict(payload["preprocessing"])
    preprocessing["resize"] = (size, size)
    preprocessing["center_crop"] = (98, 98) if family == "dinomaly" else None
    payload["preprocessing"] = preprocessing
    return ModelConfig.model_validate(payload)


def create_synthetic_dataset(
    root: Path, *, size: int
) -> tuple[DatasetManifest, tuple[Path, ...], Path]:
    from PIL import Image

    generator = np.random.default_rng(42)
    train_paths: list[Path] = []
    for index in range(2):
        path = root / f"can/train/good/{index:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        pixels = generator.integers(0, 256, size=(size, size, 3), dtype=np.uint8)
        Image.fromarray(pixels, mode="RGB").save(path)
        train_paths.append(path)
    prediction_path = root / "can/validation/good/000.png"
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    prediction_pixels = generator.integers(0, 256, size=(size, size, 3), dtype=np.uint8)
    Image.fromarray(prediction_pixels, mode="RGB").save(prediction_path)

    all_paths = (*train_paths, prediction_path)
    manifest = DatasetManifest(
        archive_url="https://example.com/synthetic-smoke.tar.gz",
        archive_size=1,
        archive_sha256="a" * 64,
        category_counts={"can": {"train/good": 2, "validation/good": 1}},
        extensions=(".png",),
        files=tuple(
            DatasetFile(
                relative_path=path.relative_to(root).as_posix(),
                size=path.stat().st_size,
                sha256=sha256_file(path),
            )
            for path in all_paths
        ),
    )
    return manifest, tuple(train_paths), prediction_path


@pytest.mark.gpu
@pytest.mark.parametrize("family", ["patchcore", "efficient_ad", "dinomaly"])
def test_model_gpu_fit_predict_export_smoke(family: str, tmp_path: Path) -> None:
    if os.environ.get("RUN_GPU_SMOKE") != "1":
        pytest.skip("set RUN_GPU_SMOKE=1 after an explicit GPU preflight")

    import torch

    assert torch.cuda.is_available()
    config = smoke_config(family)
    expected_map_shape = config.preprocessing.center_crop or config.input_size
    manifest, train_images, prediction_image = create_synthetic_dataset(
        tmp_path / "dataset", size=config.input_size[0]
    )
    auxiliary_roots: dict[str, Path] = {}
    if family == "efficient_ad":
        imagenette_text = os.environ.get("MVTECAD2_IMAGENETTE_ROOT")
        if imagenette_text is None:
            pytest.fail("MVTECAD2_IMAGENETTE_ROOT is required for EfficientAD smoke")
        auxiliary_roots["imagenette"] = Path(imagenette_text)

    adapter = create_adapter(family, config)
    fit_artifact = adapter.fit(
        FitContext(
            category="can",
            images=train_images,
            dataset_root=tmp_path / "dataset",
            dataset_manifest=manifest,
            seed=42,
            output_dir=tmp_path / "fit",
            device="cuda:0",
            auxiliary_data_roots=auxiliary_roots,
        )
    )
    prediction_artifact = adapter.predict(
        PredictContext(
            category="can",
            images=(prediction_image,),
            split="validation",
            output_dir=tmp_path / "predictions",
            model_bundle_id="gpu-smoke",
            device="cuda:0",
            expected_map_shapes=(expected_map_shape,),
            checkpoint_path=fit_artifact.checkpoint.path,
            auxiliary_data_roots=auxiliary_roots,
        )
    )
    bundle = adapter.export_bundle(
        ExportContext(
            category="can",
            checkpoint_path=fit_artifact.checkpoint.path,
            output_dir=tmp_path / "bundle",
            threshold=0.5,
            device="cuda:0",
            auxiliary_data_roots=auxiliary_roots,
        )
    )

    assert len(prediction_artifact.records) == 1
    assert np.isfinite(prediction_artifact.records[0].anomaly_score)
    anomaly_map = np.load(prediction_artifact.anomaly_maps[0].path, allow_pickle=False)
    assert anomaly_map.shape == expected_map_shape
    assert np.isfinite(anomaly_map).all()
    assert bundle.files
    assert all((tmp_path / "bundle" / item.path).is_file() for item in bundle.files)
