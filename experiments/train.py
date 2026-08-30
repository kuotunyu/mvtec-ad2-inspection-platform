from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.models.base import FitContext, load_model_config
from experiments.models.factory import create_adapter
from inspection_platform.contracts import DatasetManifest
from inspection_platform.contracts.dataset import MVTecAD2Category


def load_dataset_manifest(path: Path) -> DatasetManifest:
    """Load a manifest only when its recorded canonical identity still matches."""

    resolved = path.expanduser().resolve(strict=True)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dataset manifest root must be an object")
    canonical_identity = payload.pop("canonical_sha256", None)
    if not isinstance(canonical_identity, str):
        raise ValueError("dataset manifest must record canonical_sha256")
    manifest = DatasetManifest.model_validate(cast(dict[str, Any], payload))
    if canonical_identity != manifest.identity:
        raise ValueError("dataset manifest canonical identity does not match its contents")
    return manifest


def write_contract(path: Path, contract: BaseModel) -> Path:
    """Persist one JSON evidence contract atomically without overwriting an existing one."""

    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.exists():
        raise FileExistsError(f"artifact already exists: {resolved}")
    temporary = resolved.with_suffix(f"{resolved.suffix}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary artifact already exists: {temporary}")
    payload = contract.model_dump(mode="json")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, resolved)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return resolved


def _fit_images(
    dataset_root: Path,
    manifest: DatasetManifest,
    category: MVTecAD2Category,
) -> tuple[Path, ...]:
    prefix = f"{category}/train/good/"
    relative_paths = sorted(
        item.relative_path
        for item in manifest.files
        if item.relative_path.startswith(prefix)
        and Path(item.relative_path).suffix.lower() == ".png"
    )
    if not relative_paths:
        raise ValueError(f"manifest has no train/good PNG images for category {category}")
    return tuple((dataset_root / relative).resolve(strict=True) for relative in relative_paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train one frozen MVTec AD 2 model configuration")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--category", required=True, choices=REQUIRED_CATEGORIES)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--imagenette-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_model_config(args.config)
    dataset_root = args.dataset_root.expanduser().resolve(strict=True)
    manifest = load_dataset_manifest(args.dataset_manifest)
    category = cast(MVTecAD2Category, args.category)
    auxiliary_roots: dict[str, Path] = {}
    if args.imagenette_root is not None:
        auxiliary_roots["imagenette"] = args.imagenette_root.expanduser().resolve(strict=True)

    adapter = create_adapter(config.family, config)
    artifact = adapter.fit(
        FitContext(
            category=category,
            images=_fit_images(dataset_root, manifest, category),
            dataset_root=dataset_root,
            dataset_manifest=manifest,
            seed=args.seed,
            output_dir=args.output_dir.expanduser().resolve(),
            device=args.device,
            auxiliary_data_roots=auxiliary_roots,
        )
    )
    artifact_path = write_contract(args.output_dir / "fit-artifact.json", artifact)
    print(
        json.dumps(
            {
                "artifact": str(artifact_path),
                "category": artifact.category,
                "family": artifact.family,
                "status": "trained",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
