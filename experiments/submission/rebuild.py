from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import tifffile
from PIL import Image

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.submission.build import (
    PrivateManifest,
    PublicBoundaryError,
    SubmissionBuilder,
    SubmissionPrediction,
)
from experiments.submission.official_utils import OfficialUtilities
from experiments.submission.thresholds import (
    SubmissionThreshold,
    calibrate_submission_threshold,
)
from experiments.submission.verify import verify_archive, write_submission_summary
from experiments.train import write_contract

OFFICIAL_UTILITIES_SHA256 = "fda9b379affbbde8b4d4fc1fe6ac52aaff981f347f3424e6b6de027457549f15"


@dataclass(frozen=True, slots=True)
class FrozenChampion:
    family: str
    run_identities: tuple[str, ...]


def validate_rebuild_output(
    *,
    output_root: Path,
    source_cache_root: Path,
    repository_root: Path,
) -> Path:
    output = output_root.expanduser().resolve()
    source = source_cache_root.expanduser().resolve(strict=True)
    repository = repository_root.expanduser().resolve(strict=True)
    if output == repository or repository in output.parents:
        raise PublicBoundaryError("cache-only output must remain outside repository")
    if output == source or source in output.parents or output in source.parents:
        raise PublicBoundaryError("cache-only output must not overlap the source cache")
    if (output / "private_submission.tar.gz").exists():
        raise FileExistsError("corrected submission archive already exists")
    return output


def cached_predictions(
    *,
    manifest: PrivateManifest,
    cache_root: Path,
    dataset_root: Path,
) -> tuple[SubmissionPrediction, ...]:
    root = cache_root.expanduser().resolve(strict=True)
    data = dataset_root.expanduser().resolve(strict=True)
    expected_paths = {
        (root / category / split / "tiff" / f"{image_id}.tiff").resolve()
        for category, split, image_id in manifest.images
    }
    actual_paths = {path.resolve() for path in root.rglob("*.tiff")}
    missing = expected_paths - actual_paths
    if missing:
        raise ValueError(f"missing cached TIFF files: count={len(missing)}")
    extra = actual_paths - expected_paths
    if extra:
        raise ValueError(f"extra cached TIFF files: count={len(extra)}")

    predictions: list[SubmissionPrediction] = []
    for category, split, image_id in manifest.images:
        tiff = (root / category / split / "tiff" / f"{image_id}.tiff").resolve(strict=True)
        values = np.asarray(tifffile.imread(tiff))
        if values.dtype != np.float16:
            raise ValueError(f"cached TIFF must use float16: {category}/{split}")
        if values.ndim != 2 or not np.isfinite(values).all():
            raise ValueError(f"cached TIFF must be a finite 2D array: {category}/{split}")
        source = (data / category / split / f"{image_id}.png").resolve(strict=True)
        with Image.open(source) as image:
            width, height = image.size
        if values.shape != (height, width):
            raise ValueError(f"cached TIFF geometry differs from source PNG: {category}/{split}")
        predictions.append(
            SubmissionPrediction(
                category=category,
                split=split,
                image_id=image_id,
                anomaly_map=tiff,
            )
        )
    return tuple(predictions)


def rebuild_cached_submission(
    *,
    manifest: PrivateManifest,
    predictions: tuple[SubmissionPrediction, ...],
    thresholds: Mapping[str, SubmissionThreshold],
    output_root: Path,
    validate: Callable[[Path], None],
    repository_root: Path | None = None,
) -> Path:
    output = output_root.expanduser().resolve()
    repository = (
        Path.cwd().resolve()
        if repository_root is None
        else repository_root.expanduser().resolve(strict=True)
    )
    if output == repository or repository in output.parents:
        raise PublicBoundaryError("cache-only output must remain outside repository")
    archive_path = output / "private_submission.tar.gz"
    if archive_path.exists():
        raise FileExistsError(f"corrected submission archive already exists: {archive_path}")

    for category, threshold in sorted(thresholds.items()):
        write_contract(output / "calibrations" / f"{category}.json", threshold)
    archive = SubmissionBuilder(
        manifest=manifest,
        repository_root=repository,
    ).build(
        output_dir=output,
        predictions=predictions,
        thresholds=thresholds,
    )
    verification = verify_archive(archive, manifest, thresholds)
    with tempfile.TemporaryDirectory(prefix="thresholded-validator-", dir=output) as temp:
        extracted = Path(temp)
        with tarfile.open(archive, "r:gz") as stream:
            stream.extractall(extracted, filter="data")
        validate(extracted / archive.stem.removesuffix(".tar"))
    write_submission_summary(
        output / "submission_summary.json",
        verification,
        validator_status="LOCAL-PREFLIGHT-NOT-SUBMITTED",
    )
    return archive


def _load_champions(path: Path) -> dict[str, FrozenChampion]:
    payload = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("champions"), dict)
        or not isinstance(payload.get("decisions"), list)
    ):
        raise ValueError("champions file must contain champions and decisions")
    families = cast(dict[str, Any], payload["champions"])
    if set(families) != set(REQUIRED_CATEGORIES) or not all(
        isinstance(value, str) for value in families.values()
    ):
        raise ValueError("champion categories do not match the required dataset categories")
    decisions = {
        item.get("category"): item
        for item in cast(list[Any], payload["decisions"])
        if isinstance(item, dict) and isinstance(item.get("category"), str)
    }
    champions: dict[str, FrozenChampion] = {}
    for category in REQUIRED_CATEGORIES:
        decision = decisions.get(category)
        if not isinstance(decision, dict) or not isinstance(decision.get("candidates"), list):
            raise ValueError(f"champion decision is missing for category: {category}")
        family = cast(str, families[category])
        matches = [
            candidate
            for candidate in cast(list[Any], decision["candidates"])
            if isinstance(candidate, dict) and candidate.get("family") == family
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("run_identities"), list):
            raise ValueError(f"frozen champion runs are missing for category: {category}")
        run_identities = tuple(cast(list[str], matches[0]["run_identities"]))
        if not run_identities or any(
            len(identity) != 64
            or any(character not in "0123456789abcdef" for character in identity)
            for identity in run_identities
        ):
            raise ValueError(f"frozen champion run identity is invalid for category: {category}")
        champions[category] = FrozenChampion(
            family=family,
            run_identities=run_identities,
        )
    return champions


def frozen_champion_run(
    *,
    runs_root: Path,
    category: str,
    family: str,
    run_identities: tuple[str, ...],
) -> Path:
    root = runs_root.expanduser().resolve(strict=True)
    matches: list[Path] = []
    for identity in run_identities:
        run = root / identity
        if not run.is_dir():
            continue
        spec = json.loads((run / "spec.json").read_text(encoding="utf-8"))
        record = json.loads((run / "record.json").read_text(encoding="utf-8"))
        recorded_spec = {key: value for key, value in spec.items() if key != "canonical_sha256"}
        if (
            spec.get("canonical_sha256") == identity
            and spec.get("category") == category
            and spec.get("model_family") == family
            and spec.get("seed") == 42
            and record.get("status") == "completed"
            and record.get("spec") == recorded_spec
        ):
            matches.append(run.resolve())
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one completed frozen seed-42 champion: {category}/{family}"
        )
    return matches[0]


def rebuild_from_cache(
    *,
    data_root: Path,
    runs_root: Path,
    champions_path: Path,
    source_cache_root: Path,
    output_root: Path,
    official_utils_root: Path,
    repository_root: Path | None = None,
) -> Path:
    repository = (
        Path.cwd().resolve()
        if repository_root is None
        else repository_root.expanduser().resolve(strict=True)
    )
    output = validate_rebuild_output(
        output_root=output_root,
        source_cache_root=source_cache_root,
        repository_root=repository,
    )
    data = data_root.expanduser().resolve(strict=True)
    runs = runs_root.expanduser().resolve(strict=True)
    champions = _load_champions(champions_path)
    manifest = PrivateManifest.from_dataset_root(data)
    predictions = cached_predictions(
        manifest=manifest,
        cache_root=source_cache_root,
        dataset_root=data,
    )
    thresholds = {
        category: calibrate_submission_threshold(
            frozen_champion_run(
                runs_root=runs,
                category=category,
                family=champions[category].family,
                run_identities=champions[category].run_identities,
            )
        )
        for category in REQUIRED_CATEGORIES
    }
    utilities = OfficialUtilities.from_directory(
        official_utils_root,
        archive_sha256=OFFICIAL_UTILITIES_SHA256,
    )
    return rebuild_cached_submission(
        manifest=manifest,
        predictions=predictions,
        thresholds=thresholds,
        output_root=output,
        validate=utilities.validate,
        repository_root=repository,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild a thresholded MVTec AD 2 archive from the frozen TIFF cache"
    )
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--champions", required=True, type=Path)
    parser.add_argument("--source-cache-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--official-utils-root", required=True, type=Path)
    return parser


def main(argv: tuple[str, ...] | None = None) -> int:
    args = build_parser().parse_args(argv)
    archive = rebuild_from_cache(
        data_root=args.data_root,
        runs_root=args.runs_root,
        champions_path=args.champions,
        source_cache_root=args.source_cache_root,
        output_root=args.output_root,
        official_utils_root=args.official_utils_root,
    )
    print(json.dumps({"archive": str(archive), "status": "local-preflight"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
