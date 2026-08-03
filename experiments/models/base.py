from __future__ import annotations

import importlib.metadata
import math
import os
import platform
import random
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Self, cast

import numpy as np
import yaml  # type: ignore[import-untyped]
from numpy.typing import NDArray
from pydantic import Field, JsonValue, computed_field, model_validator

from inspection_platform.contracts import (
    BundleFile,
    DatasetManifest,
    ModelBundleManifest,
    ModelFamily,
    PredictionRecord,
    canonical_hash,
    sha256_file,
)
from inspection_platform.contracts._base import ContractModel
from inspection_platform.contracts.dataset import MVTecAD2Category, Sha256

PredictionSplit = Literal["validation", "test_public", "test_private", "test_private_mixed"]


class SplitLeakageError(RuntimeError):
    """Raised when fit inputs are not frozen normal training images."""


class AdapterContractError(ValueError):
    """Raised when an upstream adapter violates project-owned output contracts."""


class TrainerLimits(ContractModel):
    max_epochs: Annotated[int, Field(gt=0)]
    max_steps: Annotated[int | None, Field(gt=0)] = None


class PreprocessingConfig(ContractModel):
    resize: Annotated[tuple[int, int], Field(min_length=2, max_length=2)]
    normalization: Literal["imagenet", "none"]
    interpolation: Literal["bilinear", "bicubic"] = "bilinear"
    center_crop: Annotated[tuple[int, int] | None, Field(min_length=2, max_length=2)] = None

    @model_validator(mode="after")
    def require_positive_size(self) -> Self:
        if any(dimension <= 0 for dimension in self.resize):
            raise ValueError("preprocessing resize dimensions must be positive")
        if self.center_crop is not None:
            if any(dimension <= 0 for dimension in self.center_crop):
                raise ValueError("preprocessing center-crop dimensions must be positive")
            if any(
                crop > resize for crop, resize in zip(self.center_crop, self.resize, strict=True)
            ):
                raise ValueError("preprocessing center crop must not exceed resize dimensions")
        return self


class CheckpointPolicy(ContractModel):
    mode: Literal["best", "last"]
    save_top_k: Literal[1] = 1


class ModelConfig(ContractModel):
    """Canonical, seed-free model configuration loaded from a pinned YAML file."""

    family: ModelFamily
    anomalib_version: Literal["2.5.0"]
    model_name: str
    backbone: str | None
    input_size: Annotated[tuple[int, int], Field(min_length=2, max_length=2)]
    batch_size: Annotated[int, Field(gt=0)]
    oom_fallback_batch_size: Annotated[int | None, Field(gt=0)] = None
    precision: Literal["32-true", "16-mixed", "bf16-mixed"]
    trainer_limits: TrainerLimits
    seed: None = None
    preprocessing: PreprocessingConfig
    checkpoint_policy: CheckpointPolicy
    export_mode: Literal["torch", "onnx", "openvino"]
    family_options: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_positive_input_size(self) -> Self:
        if any(dimension <= 0 for dimension in self.input_size):
            raise ValueError("input_size dimensions must be positive")
        if self.input_size != self.preprocessing.resize:
            raise ValueError("input_size must match preprocessing resize")
        if (
            self.oom_fallback_batch_size is not None
            and self.oom_fallback_batch_size > self.batch_size
        ):
            raise ValueError("oom_fallback_batch_size must not exceed batch_size")
        if self.family == "efficient_ad":
            if self.batch_size != 1:
                raise ValueError("EfficientAD requires batch_size 1 in Anomalib 2.5.0")
            if self.preprocessing.normalization != "none":
                raise ValueError("EfficientAD applies ImageNet normalization inside the model")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        return canonical_hash(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def preprocessing_sha256(self) -> str:
        return canonical_hash(self.preprocessing)


def load_model_config(path: Path) -> ModelConfig:
    """Load one strict YAML document into the canonical model configuration."""

    path = path.expanduser().resolve(strict=True)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("model config YAML root must be a mapping")
    return ModelConfig.model_validate(cast(dict[str, Any], payload))


@dataclass(frozen=True, slots=True)
class FitContext:
    category: MVTecAD2Category
    images: tuple[Path, ...]
    dataset_root: Path
    dataset_manifest: DatasetManifest
    seed: int
    output_dir: Path
    device: str
    auxiliary_data_roots: Mapping[str, Path] = dataclass_field(default_factory=dict)
    resume_checkpoint: Path | None = None


@dataclass(frozen=True, slots=True)
class PredictContext:
    category: MVTecAD2Category
    images: tuple[Path, ...]
    split: PredictionSplit
    output_dir: Path
    model_bundle_id: str
    device: str
    expected_map_shapes: tuple[tuple[int, int], ...] | None = None
    checkpoint_path: Path | None = None
    auxiliary_data_roots: Mapping[str, Path] = dataclass_field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExportContext:
    category: MVTecAD2Category
    checkpoint_path: Path
    output_dir: Path
    threshold: float
    device: str
    auxiliary_data_roots: Mapping[str, Path] = dataclass_field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawPrediction:
    input_path: Path
    anomaly_score: float
    anomaly_map: NDArray[np.float32] | NDArray[np.float64]


class ArtifactFile(ContractModel):
    path: Path
    sha256: Sha256
    size: Annotated[int, Field(ge=0)]


class FitArtifact(ContractModel):
    family: ModelFamily
    category: MVTecAD2Category
    checkpoint: ArtifactFile
    config_sha256: Sha256
    preprocessing_sha256: Sha256
    seed: int
    device: str
    environment: dict[str, str]


class PredictionArtifact(ContractModel):
    family: ModelFamily
    category: MVTecAD2Category
    split: PredictionSplit
    config_sha256: Sha256
    records: tuple[PredictionRecord, ...]
    anomaly_maps: tuple[ArtifactFile, ...]

    @model_validator(mode="after")
    def require_aligned_artifacts(self) -> Self:
        if len(self.records) != len(self.anomaly_maps):
            raise ValueError("prediction records and anomaly maps must have the same length")
        for record, anomaly_map in zip(self.records, self.anomaly_maps, strict=True):
            if record.anomaly_map_sha256 != anomaly_map.sha256:
                raise ValueError("prediction record and anomaly-map hash differ")
        return self


def assert_fit_split(context: FitContext) -> None:
    """Verify every fit image against the manifest and the category train/good split."""

    if not context.images:
        raise SplitLeakageError("fit inputs must not be empty")
    root = context.dataset_root.expanduser().resolve(strict=True)
    manifest_files = {item.relative_path: item for item in context.dataset_manifest.files}
    for image in context.images:
        resolved = image.expanduser().resolve(strict=True)
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as error:
            raise SplitLeakageError("fit input is outside the frozen dataset root") from error
        manifest_file = manifest_files.get(relative)
        if manifest_file is None:
            raise SplitLeakageError("fit input is absent from the frozen dataset manifest")
        parts = Path(relative).parts
        if parts[:3] != (context.category, "train", "good"):
            raise SplitLeakageError("fit inputs must come only from the category train/good split")
        if (
            resolved.stat().st_size != manifest_file.size
            or sha256_file(resolved) != manifest_file.sha256
        ):
            raise SplitLeakageError("fit input identity differs from the frozen dataset manifest")


def capture_environment(device: str) -> dict[str, str]:
    """Capture a bounded, non-secret runtime identity for evidence artifacts."""

    try:
        anomalib_version = importlib.metadata.version("anomalib")
    except importlib.metadata.PackageNotFoundError:
        anomalib_version = "not-installed"
    return {
        "anomalib": anomalib_version,
        "device": device,
        "machine": platform.machine(),
        "platform": platform.system(),
        "python": platform.python_version(),
    }


def seed_runtime(seed: int) -> None:
    """Set deterministic random sources shared by all family adapters."""

    random.seed(seed)
    np.random.seed(seed % (2**32))
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False


class AnomalyExperimentAdapter(ABC):
    """Validated project boundary around one approved Anomalib model family."""

    family: ClassVar[ModelFamily]

    def __init__(self, config: ModelConfig) -> None:
        if config.family != self.family:
            raise ValueError(
                f"adapter family {self.family!r} does not match config family {config.family!r}"
            )
        self.config = config

    def fit(self, context: FitContext) -> FitArtifact:
        assert_fit_split(context)
        seed_runtime(context.seed)
        checkpoint = self._fit_model(context).expanduser().resolve(strict=True)
        return FitArtifact(
            family=self.family,
            category=context.category,
            checkpoint=ArtifactFile(
                path=checkpoint,
                sha256=sha256_file(checkpoint),
                size=checkpoint.stat().st_size,
            ),
            config_sha256=self.config.identity,
            preprocessing_sha256=self.config.preprocessing_sha256,
            seed=context.seed,
            device=context.device,
            environment=capture_environment(context.device),
        )

    def predict(self, context: PredictContext) -> PredictionArtifact:
        if not context.images:
            raise AdapterContractError("prediction inputs must not be empty")
        if context.expected_map_shapes is not None and len(context.expected_map_shapes) != len(
            context.images
        ):
            raise AdapterContractError("expected map shapes must match prediction inputs")
        for image in context.images:
            image.expanduser().resolve(strict=True)

        raw_predictions = tuple(self._predict_model(context))
        if len(raw_predictions) != len(context.images):
            raise AdapterContractError("adapter output count differs from input count")

        destination = context.output_dir.expanduser().resolve()
        if destination.exists():
            raise AdapterContractError(f"prediction destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.predict-", dir=destination.parent)
        )
        records: list[PredictionRecord] = []
        maps: list[ArtifactFile] = []
        try:
            for index, (requested, raw) in enumerate(
                zip(context.images, raw_predictions, strict=True)
            ):
                if raw.input_path != requested:
                    raise AdapterContractError("adapter changed prediction input order")
                if not math.isfinite(raw.anomaly_score):
                    raise AdapterContractError("adapter returned a non-finite anomaly score")
                anomaly_map = np.asarray(raw.anomaly_map, dtype=np.float32)
                if anomaly_map.ndim != 2 or not np.isfinite(anomaly_map).all():
                    raise AdapterContractError("adapter returned an invalid anomaly map")
                if (
                    context.expected_map_shapes is not None
                    and anomaly_map.shape != context.expected_map_shapes[index]
                ):
                    raise AdapterContractError("adapter returned an incorrectly shaped anomaly map")

                name = f"{index:06d}-{requested.stem}.npy"
                temporary_path = temporary / name
                with temporary_path.open("xb") as stream:
                    np.save(stream, anomaly_map, allow_pickle=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                digest = sha256_file(temporary_path)
                final_path = destination / name
                maps.append(
                    ArtifactFile(path=final_path, sha256=digest, size=temporary_path.stat().st_size)
                )
                records.append(
                    PredictionRecord(
                        input_id=f"{index:06d}:{requested.name}",
                        input_sha256=sha256_file(requested),
                        category=context.category,
                        anomaly_score=raw.anomaly_score,
                        anomaly_map_sha256=digest,
                        model_bundle_id=context.model_bundle_id,
                        input_path=requested,
                    )
                )
            os.replace(temporary, destination)
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise

        return PredictionArtifact(
            family=self.family,
            category=context.category,
            split=context.split,
            config_sha256=self.config.identity,
            records=tuple(records),
            anomaly_maps=tuple(maps),
        )

    def export_bundle(self, context: ExportContext) -> ModelBundleManifest:
        if not math.isfinite(context.threshold):
            raise AdapterContractError("bundle threshold must be finite")
        output_root = context.output_dir.expanduser().resolve()
        if output_root.exists():
            raise AdapterContractError(f"bundle destination already exists: {output_root}")
        files = tuple(
            path.expanduser().resolve(strict=True) for path in self._export_model(context)
        )
        output_root = output_root.resolve(strict=True)
        bundle_files: list[BundleFile] = []
        for path in files:
            try:
                relative = path.relative_to(output_root).as_posix()
            except ValueError as error:
                raise AdapterContractError("exported file is outside the bundle root") from error
            bundle_files.append(
                BundleFile(path=relative, sha256=sha256_file(path), size=path.stat().st_size)
            )
        if not bundle_files:
            raise AdapterContractError("adapter exported an empty model bundle")
        return ModelBundleManifest(
            category=context.category,
            runtime_kind="anomalib",
            model_family=self.family,
            files=tuple(bundle_files),
            preprocessing_sha256=self.config.preprocessing_sha256,
            threshold=context.threshold,
        )

    @abstractmethod
    def _fit_model(self, context: FitContext) -> Path:
        """Fit the upstream model and return the finalized checkpoint path."""

    @abstractmethod
    def _predict_model(self, context: PredictContext) -> Sequence[RawPrediction]:
        """Return raw predictions in exactly the requested input order."""

    @abstractmethod
    def _export_model(self, context: ExportContext) -> Sequence[Path]:
        """Export serving files below the requested bundle root."""


class AnomalibEngineAdapter(AnomalyExperimentAdapter, ABC):
    """Shared Anomalib 2.5 Engine translation with exact-path prediction ordering."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self._checkpoint_path: Path | None = None

    @abstractmethod
    def model_kwargs(self, auxiliary_data_roots: Mapping[str, Path]) -> dict[str, object]:
        """Translate the frozen project config to one version-pinned constructor."""

    @abstractmethod
    def _build_model(self, auxiliary_data_roots: Mapping[str, Path]) -> Any:
        """Construct the installed Anomalib 2.5 model lazily."""

    def _training_directory(self, context: FitContext) -> Path:
        resolved_images = tuple(image.expanduser().resolve(strict=True) for image in context.images)
        parents = {image.parent for image in resolved_images}
        if len(parents) != 1:
            raise SplitLeakageError("fit images must share one exact train/good directory")
        directory = parents.pop()
        discovered = tuple(sorted(directory.glob("*.png")))
        if discovered != tuple(sorted(resolved_images)):
            raise SplitLeakageError(
                "fit context must list every PNG in the verified train/good directory"
            )
        return directory

    @staticmethod
    def _trainer_device(device: str) -> tuple[str, int | list[int]]:
        if device == "cpu":
            return "cpu", 1
        prefix = "cuda:"
        if device.startswith(prefix) and device.removeprefix(prefix).isdigit():
            return "gpu", [int(device.removeprefix(prefix))]
        raise AdapterContractError(
            "device must be 'cpu' or an indexed CUDA device such as 'cuda:0'"
        )

    def _checkpoint_candidate(self, callback: Any) -> Path | None:
        checkpoint_text = (
            callback.best_model_path
            if self.config.checkpoint_policy.mode == "best"
            else callback.last_model_path
        )
        return Path(checkpoint_text) if checkpoint_text else None

    def _engine(self, *, root: Path, device: str, callbacks: list[Any] | None = None) -> Any:
        from anomalib.engine import Engine

        accelerator, devices = self._trainer_device(device)
        max_steps = self.config.trainer_limits.max_steps
        return Engine(
            accelerator=accelerator,
            callbacks=callbacks,
            default_root_dir=root,
            deterministic=True,
            devices=devices,
            enable_progress_bar=False,
            limit_val_batches=0,
            logger=False,
            max_epochs=self.config.trainer_limits.max_epochs,
            max_steps=-1 if max_steps is None else max_steps,
            precision=self.config.precision,
        )

    def _fit_model(self, context: FitContext) -> Path:
        from anomalib.callbacks import ModelCheckpoint
        from anomalib.data import Folder

        output_dir = context.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_dir = output_dir / "checkpoints"
        if checkpoint_dir.exists():
            raise AdapterContractError(f"checkpoint directory already exists: {checkpoint_dir}")
        checkpoint_callback = ModelCheckpoint(
            dirpath=checkpoint_dir,
            filename="model",
            save_last=True,
            save_top_k=1,
        )
        datamodule = Folder(
            name=f"mvtec-ad2-{context.category}",
            normal_dir=self._training_directory(context),
            train_batch_size=self.config.batch_size,
            eval_batch_size=1,
            num_workers=0,
            test_split_mode="none",
            val_split_mode="none",
            seed=context.seed,
        )
        model = self._build_model(context.auxiliary_data_roots)
        engine = self._engine(
            root=output_dir,
            device=context.device,
            callbacks=[checkpoint_callback],
        )
        resume_checkpoint = (
            context.resume_checkpoint.expanduser().resolve(strict=True)
            if context.resume_checkpoint is not None
            else None
        )
        engine.fit(model=model, datamodule=datamodule, ckpt_path=resume_checkpoint)
        checkpoint = self._checkpoint_candidate(checkpoint_callback)
        if checkpoint is None:
            candidates = tuple(sorted(checkpoint_dir.glob("*.ckpt")))
            if len(candidates) != 1:
                raise AdapterContractError(
                    "Anomalib fit did not produce the checkpoint required by its frozen policy"
                )
            checkpoint = candidates[0]
        self._checkpoint_path = checkpoint.expanduser().resolve(strict=True)
        return self._checkpoint_path

    @staticmethod
    def _prediction_items(predictions: Any) -> list[Any]:
        items: list[Any] = []
        for prediction in predictions or []:
            if isinstance(prediction, list):
                items.extend(AnomalibEngineAdapter._prediction_items(prediction))
            elif isinstance(getattr(prediction, "image_path", None), list):
                items.extend(list(prediction))
            else:
                items.append(prediction)
        return items

    @staticmethod
    def _scalar(value: Any, *, name: str) -> float:
        if hasattr(value, "detach"):
            value = value.detach().cpu().numpy()
        array = np.asarray(value)
        if array.size != 1:
            raise AdapterContractError(f"Anomalib {name} is not scalar")
        return float(array.reshape(-1)[0])

    @staticmethod
    def _map(value: Any) -> NDArray[np.float32]:
        if hasattr(value, "detach"):
            value = value.detach().cpu().numpy()
        array = np.asarray(value, dtype=np.float32).squeeze()
        if array.ndim != 2:
            raise AdapterContractError("Anomalib anomaly map is not two-dimensional")
        return array

    def _predict_model(self, context: PredictContext) -> Sequence[RawPrediction]:
        from anomalib.data import PredictDataset

        checkpoint = context.checkpoint_path or self._checkpoint_path
        if checkpoint is None:
            raise AdapterContractError("checkpoint_path is required for prediction")
        checkpoint = checkpoint.expanduser().resolve(strict=True)

        class OrderedPredictDataset:
            def __init__(self, images: tuple[Path, ...], image_size: tuple[int, int]) -> None:
                self._datasets = tuple(
                    PredictDataset(path=image, image_size=image_size) for image in images
                )

            def __len__(self) -> int:
                return len(self._datasets)

            def __getitem__(self, index: int) -> Any:
                return self._datasets[index][0]

            @property
            def collate_fn(self) -> Any:
                return self._datasets[0].collate_fn

        model = self._build_model(context.auxiliary_data_roots)
        engine = self._engine(root=context.output_dir.parent, device=context.device)
        dataset = OrderedPredictDataset(context.images, self.config.input_size)
        predictions = engine.predict(
            model=model,
            dataset=dataset,
            return_predictions=True,
            ckpt_path=checkpoint,
        )
        items = self._prediction_items(predictions)
        return tuple(
            RawPrediction(
                input_path=Path(item.image_path),
                anomaly_score=self._scalar(item.pred_score, name="prediction score"),
                anomaly_map=self._map(item.anomaly_map),
            )
            for item in items
        )

    def _export_model(self, context: ExportContext) -> Sequence[Path]:
        from anomalib.deploy import ExportType

        checkpoint = context.checkpoint_path.expanduser().resolve(strict=True)
        output_dir = context.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        model = self._build_model(context.auxiliary_data_roots)
        engine = self._engine(root=output_dir, device=context.device)
        exported = engine.export(
            model=model,
            export_type=ExportType.TORCH,
            export_root=output_dir,
            model_file_name="model",
            input_size=self.config.input_size,
            ckpt_path=checkpoint,
        )
        if exported is None:
            raise AdapterContractError("Anomalib export did not return an artifact path")
        return (Path(exported),)
