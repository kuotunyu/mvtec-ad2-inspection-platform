from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.models.base import PredictContext, PredictionSplit, load_model_config
from experiments.models.factory import create_adapter
from experiments.train import write_contract
from inspection_platform.contracts.dataset import MVTecAD2Category

PREDICTION_SPLITS: tuple[PredictionSplit, ...] = (
    "validation",
    "test_public",
    "test_private",
    "test_private_mixed",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Predict with one frozen MVTec AD 2 model")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--category", required=True, choices=REQUIRED_CATEGORIES)
    parser.add_argument("--split", required=True, choices=PREDICTION_SPLITS)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--model-bundle-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--images", required=True, nargs="+", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--imagenette-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_model_config(args.config)
    images = tuple(path.expanduser().resolve(strict=True) for path in args.images)
    expected_shape = config.preprocessing.center_crop or config.input_size
    auxiliary_roots: dict[str, Path] = {}
    if args.imagenette_root is not None:
        auxiliary_roots["imagenette"] = args.imagenette_root.expanduser().resolve(strict=True)

    adapter = create_adapter(config.family, config)
    artifact = adapter.predict(
        PredictContext(
            category=cast(MVTecAD2Category, args.category),
            images=images,
            split=cast(PredictionSplit, args.split),
            output_dir=args.output_dir.expanduser().resolve(),
            model_bundle_id=args.model_bundle_id,
            device=args.device,
            expected_map_shapes=tuple(expected_shape for _ in images),
            checkpoint_path=args.checkpoint.expanduser().resolve(strict=True),
            auxiliary_data_roots=auxiliary_roots,
        )
    )
    artifact_path = write_contract(args.output_dir / "prediction-artifact.json", artifact)
    print(
        json.dumps(
            {
                "artifact": str(artifact_path),
                "category": artifact.category,
                "count": len(artifact.records),
                "family": artifact.family,
                "status": "predicted",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
