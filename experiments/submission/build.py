from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile
from typing import Any, cast

import numpy as np
import tifffile
from PIL import Image

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.models.base import ModelConfig, PredictContext, PredictionArtifact
from experiments.models.factory import create_adapter
from experiments.orchestration.gpu_lock import GpuLease
from experiments.submission.thresholds import (
    SubmissionThreshold,
    calibrate_submission_threshold,
)
from experiments.train import write_contract
from inspection_platform.contracts import MVTecAD2Category

TestSplit = str
ImageIdentity = tuple[str, str, str]


class PublicBoundaryError(RuntimeError):
    """Raised when private artifacts would be written inside the repository."""


@dataclass(frozen=True, slots=True)
class SubmissionPrediction:
    category: str
    split: TestSplit
    image_id: str
    anomaly_map: Path

    @property
    def identity(self) -> ImageIdentity:
        return (self.category, self.split, self.image_id)


@dataclass(frozen=True, slots=True)
class PrivateManifest:
    images: tuple[ImageIdentity, ...]

    def __post_init__(self) -> None:
        if len(set(self.images)) != len(self.images):
            raise ValueError("duplicate private image identity")
        for category, split, image_id in self.images:
            if category not in REQUIRED_CATEGORIES:
                raise ValueError(f"unsupported category: {category}")
            if split not in {"test_private", "test_private_mixed"}:
                raise ValueError(f"unsupported private split: {split}")
            if not image_id or Path(image_id).name != image_id:
                raise ValueError("image_id must be a non-empty file stem")

    @classmethod
    def from_dataset_root(cls, root: Path) -> PrivateManifest:
        resolved = root.expanduser().resolve(strict=True)
        images: list[ImageIdentity] = []
        for category in REQUIRED_CATEGORIES:
            for split in ("test_private", "test_private_mixed"):
                paths = sorted((resolved / category / split).glob("*.png"))
                if not paths:
                    raise ValueError(f"private split is empty: {category}/{split}")
                images.extend((category, split, path.stem) for path in paths)
        return cls(images=tuple(images))


@dataclass(frozen=True, slots=True)
class SubmissionInspection:
    continuous_image_ids: tuple[str, ...]
    thresholded_image_ids: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_submission(archive: Path) -> SubmissionInspection:
    continuous: list[str] = []
    thresholded: list[str] = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            path = Path(member.name)
            parts = path.parts
            if len(parts) == 5 and parts[1] == "anomaly_images" and path.suffix == ".tiff":
                continuous.append("/".join(parts[2:]).removesuffix(".tiff"))
            elif (
                len(parts) == 5
                and parts[1] == "anomaly_images_thresholded"
                and path.suffix == ".png"
            ):
                thresholded.append("/".join(parts[2:]).removesuffix(".png"))
    return SubmissionInspection(
        continuous_image_ids=tuple(sorted(continuous)),
        thresholded_image_ids=tuple(sorted(thresholded)),
    )


class SubmissionBuilder:
    def __init__(
        self,
        *,
        manifest: PrivateManifest,
        repository_root: Path | None = None,
    ) -> None:
        self.manifest = manifest
        self.repository_root = (
            repository_root.expanduser().resolve()
            if repository_root is not None
            else Path.cwd().resolve()
        )

    def build(
        self,
        *,
        output_dir: Path,
        predictions: tuple[SubmissionPrediction, ...],
        thresholds: Mapping[str, SubmissionThreshold],
        archive_name: str = "private_submission",
    ) -> Path:
        output = output_dir.expanduser().resolve()
        if output == self.repository_root or self.repository_root in output.parents:
            raise PublicBoundaryError("private output must be outside repository")

        expected = set(self.manifest.images)
        actual = [prediction.identity for prediction in predictions]
        if len(set(actual)) != len(actual):
            raise ValueError("duplicate prediction identity")
        if set(actual) != expected:
            raise ValueError("prediction identities do not match private manifest")
        expected_categories = {category for category, _split, _image_id in expected}
        if set(thresholds) != expected_categories:
            raise ValueError("threshold categories do not match private manifest")
        if any(threshold.category != category for category, threshold in thresholds.items()):
            raise ValueError("threshold contract category does not match its mapping key")
        output.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=f"{archive_name}-", dir=output) as temp:
            staging = Path(temp) / archive_name
            for prediction in predictions:
                source = prediction.anomaly_map.expanduser().resolve(strict=True)
                if source.suffix.lower() != ".tiff":
                    raise ValueError("anomaly maps must be TIFF files")
                values = np.asarray(tifffile.imread(source))
                if values.dtype != np.float16 or values.ndim != 2 or not np.isfinite(values).all():
                    raise ValueError("anomaly maps must be finite 2D float16 arrays")
                destination = (
                    staging
                    / "anomaly_images"
                    / prediction.category
                    / prediction.split
                    / f"{prediction.image_id}.tiff"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                copyfile(source, destination)
                thresholded = np.where(
                    values > thresholds[prediction.category].threshold,
                    255,
                    0,
                ).astype(np.uint8)
                thresholded_destination = (
                    staging
                    / "anomaly_images_thresholded"
                    / prediction.category
                    / prediction.split
                    / f"{prediction.image_id}.png"
                )
                thresholded_destination.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(thresholded, mode="L").save(thresholded_destination)

            archive = output / f"{archive_name}.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        tar.add(path, arcname=path.relative_to(staging.parent))
            archive.with_suffix(archive.suffix + ".sha256").write_text(
                f"{_sha256(archive)}  {archive.name}\n", encoding="utf-8"
            )
        return archive


def _private_images(data_root: Path, category: str, split: str) -> tuple[Path, ...]:
    paths = tuple(sorted((data_root / category / split).glob("*.png")))
    if not paths:
        raise ValueError(f"private split is empty: {category}/{split}")
    return paths


def _champion_run(runs_root: Path, category: str, family: str) -> Path:
    for spec_path in runs_root.glob("*/spec.json"):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if (
            spec.get("category") == category
            and spec.get("model_family") == family
            and spec.get("seed") == 42
        ):
            record = json.loads((spec_path.parent / "record.json").read_text(encoding="utf-8"))
            if record.get("status") != "completed":
                raise RuntimeError(f"champion run is not completed: {spec_path.parent.name}")
            return spec_path.parent
    raise FileNotFoundError(f"seed-42 champion run not found: {category}/{family}")


def _source_geometry_map(source: Path, anomaly_map: np.ndarray) -> np.ndarray:
    with Image.open(source) as image:
        width, height = image.size
    checked = np.asarray(anomaly_map, dtype=np.float32)
    if checked.shape != (height, width):
        resized = Image.fromarray(checked, mode="F").resize(
            (width, height), Image.Resampling.BILINEAR
        )
        checked = np.asarray(resized, dtype=np.float32)
    if checked.ndim != 2 or not np.isfinite(checked).all():
        raise ValueError(f"invalid anomaly map for {source}")
    return checked.astype(np.float16, copy=False)


def _predict_split(
    *,
    category: str,
    family: str,
    split: str,
    data_root: Path,
    manifest_path: Path,
    runs_root: Path,
    imagenette_root: Path,
    cache_root: Path,
    device: str,
) -> tuple[SubmissionPrediction, ...]:
    run_dir = _champion_run(runs_root, category, family)
    config_payload = json.loads(
        (run_dir / "attempts" / "attempt-1" / "config.json").read_text(encoding="utf-8")
    )
    config = load_model_config_from_payload(config_payload)
    images = _private_images(data_root, category, split)
    artifact_path = cache_root / category / split / "prediction-artifact.json"
    if artifact_path.exists():
        artifact = PredictionArtifact.model_validate_json(artifact_path.read_text(encoding="utf-8"))
    else:
        output_dir = artifact_path.parent / "prediction-maps"
        adapter = create_adapter(cast(Any, family), config)
        artifact = adapter.predict(
            PredictContext(
                category=cast(MVTecAD2Category, category),
                images=images,
                split=cast(Any, split),
                output_dir=output_dir,
                model_bundle_id=run_dir.name,
                device=device,
                checkpoint_path=(run_dir / "checkpoints" / "model.ckpt").resolve(strict=True),
                auxiliary_data_roots={"imagenette": imagenette_root},
            )
        )
        write_contract(artifact_path, artifact)

    if len(artifact.records) != len(images):
        raise ValueError(f"prediction count mismatch for {category}/{split}")
    map_root = cache_root / category / split / "tiff"
    predictions: list[SubmissionPrediction] = []
    for image, _record, map_file in zip(
        images, artifact.records, artifact.anomaly_maps, strict=True
    ):
        source_map = map_file.path.expanduser().resolve(strict=True)
        values = _source_geometry_map(image, np.load(source_map, allow_pickle=False))
        destination = map_root / f"{image.stem}.tiff"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            tifffile.imwrite(destination, values)
        predictions.append(
            SubmissionPrediction(
                category=category,
                split=split,
                image_id=image.stem,
                anomaly_map=destination,
            )
        )
    return tuple(predictions)


def load_model_config_from_payload(payload: dict[str, Any]) -> ModelConfig:
    """Validate the immutable model config copied into a completed run."""

    config = payload.get("config", payload)
    return load_model_config_from_dict(cast(dict[str, Any], config))


def load_model_config_from_dict(payload: dict[str, Any]) -> ModelConfig:
    return ModelConfig.model_validate(payload)


def build_formal_submission(
    *,
    data_root: Path,
    runs_root: Path,
    evidence_root: Path,
    manifest_path: Path,
    output_root: Path,
    imagenette_root: Path,
    gpu_lock: Path,
    official_utils_root: Path,
    device: str = "cuda:0",
) -> Path:
    from experiments.submission.official_utils import OfficialUtilities
    from experiments.submission.verify import verify_archive, write_submission_summary

    output_root = output_root.expanduser().resolve()
    if output_root == Path.cwd().resolve() or Path.cwd().resolve() in output_root.parents:
        raise PublicBoundaryError("submission output must remain outside repository")
    output_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output_root).free < 160 * 1024**3:
        raise RuntimeError("at least 160 GiB free space is required for private bundles")
    champions = json.loads((evidence_root / "champions.json").read_text(encoding="utf-8"))[
        "champions"
    ]
    manifest = PrivateManifest.from_dataset_root(data_root)
    thresholds = {
        category: calibrate_submission_threshold(
            _champion_run(runs_root, category, champions[category])
        )
        for category in REQUIRED_CATEGORIES
    }
    cache_root = output_root / "prediction-cache"
    predictions: list[SubmissionPrediction] = []
    repository_identity = hashlib.sha256(str(Path.cwd().resolve()).encode("utf-8")).hexdigest()
    with GpuLease(gpu_lock.expanduser().resolve(), repository_identity=repository_identity).acquire(
        "private-submission"
    ) as lease:
        for category in REQUIRED_CATEGORIES:
            family = champions[category]
            for split in ("test_private", "test_private_mixed"):
                predictions.extend(
                    _predict_split(
                        category=category,
                        family=family,
                        split=split,
                        data_root=data_root,
                        manifest_path=manifest_path,
                        runs_root=runs_root,
                        imagenette_root=imagenette_root,
                        cache_root=cache_root,
                        device=device,
                    )
                )
                lease.heartbeat()
    archive = SubmissionBuilder(manifest=manifest).build(
        output_dir=output_root,
        predictions=tuple(predictions),
        thresholds=thresholds,
        archive_name="private_submission",
    )
    verification = verify_archive(archive, manifest, thresholds)
    with tempfile.TemporaryDirectory(prefix="private-validator-", dir=output_root) as temp:
        extracted = Path(temp)
        with tarfile.open(archive, "r:gz") as stream:
            stream.extractall(extracted)
        submission_dir = extracted / archive.stem.removesuffix(".tar")
        OfficialUtilities.from_directory(
            official_utils_root,
            archive_sha256=("fda9b379affbbde8b4d4fc1fe6ac52aaff981f347f3424e6b6de027457549f15"),
        ).validate(submission_dir)
    write_submission_summary(
        output_root / "submission_summary.json",
        verification,
        validator_status="PASS",
    )
    return archive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build official private MVTec AD 2 predictions")
    parser.add_argument("--test-type", choices=("all", "private", "private_mixed"), default="all")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--imagenette-root", required=True, type=Path)
    parser.add_argument("--gpu-lock", required=True, type=Path)
    parser.add_argument("--official-utils-root", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    return parser


def main(argv: tuple[str, ...] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.test_type != "all":
        raise ValueError(
            "the official validator requires one combined archive containing both private splits"
        )
    archive = build_formal_submission(
        data_root=args.data_root,
        runs_root=args.runs_root,
        evidence_root=args.evidence_root,
        manifest_path=args.dataset_manifest,
        output_root=args.output_root,
        imagenette_root=args.imagenette_root,
        gpu_lock=args.gpu_lock,
        official_utils_root=args.official_utils_root,
        device=args.device,
    )
    print(json.dumps({"archive": str(archive), "status": "built"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
