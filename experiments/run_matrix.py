from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import numpy as np
from pydantic import JsonValue

from experiments.metrics.artifacts import ThresholdResult
from experiments.metrics.thresholds import conformal_upper_threshold
from experiments.models.base import (
    AnomalyExperimentAdapter,
    ArtifactFile,
    FitArtifact,
    FitContext,
    ModelConfig,
    PredictContext,
    PredictionArtifact,
    PredictionSplit,
    load_model_config,
)
from experiments.models.factory import create_adapter
from experiments.orchestration.gpu_lock import GpuLease
from experiments.orchestration.queue import ExperimentStage, expand_stage
from experiments.orchestration.supervisor import (
    ExecutionResult,
    FailureKind,
    RunRequest,
    RunStore,
    SubprocessExecutor,
    Supervisor,
)
from experiments.train import load_dataset_manifest, write_contract
from inspection_platform.contracts import (
    DatasetManifest,
    ModelFamily,
    RunSpec,
    sha256_file,
)
from inspection_platform.contracts.dataset import MVTecAD2Category

CONFIG_ROOT = Path(__file__).resolve().parent / "configs" / "models"


def _canonical_json_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_atomic_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary JSON artifact already exists: {temporary}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def _freeze_queue(
    root: Path,
    *,
    stage: ExperimentStage,
    queue: Sequence[RunSpec],
    code_revision: str,
) -> Path:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "stage": stage.model_dump(mode="json", exclude_computed_fields=True),
        "code_revision": code_revision,
        "runs": [
            spec.model_dump(mode="json", exclude_computed_fields=True) for spec in queue
        ],
    }
    payload["canonical_sha256"] = _canonical_json_hash(payload)
    path = root / f"queue-{stage.name}.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != payload:
            raise ValueError("existing frozen queue differs from requested stage")
        return path
    return _write_atomic_json(path, payload)


def _load_contenders(
    path: Path, *, dataset_manifest_sha256: str
) -> dict[MVTecAD2Category, tuple[ModelFamily, ModelFamily]]:
    payload = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("contenders artifact root must be an object")
    canonical = payload.pop("canonical_sha256", None)
    if canonical != _canonical_json_hash(payload):
        raise ValueError("contenders artifact canonical identity mismatch")
    if payload.get("dataset_manifest_sha256") != dataset_manifest_sha256:
        raise ValueError("contenders artifact dataset identity mismatch")
    contenders = payload.get("contenders")
    if not isinstance(contenders, dict):
        raise ValueError("contenders artifact must contain a contenders object")
    return cast(
        dict[MVTecAD2Category, tuple[ModelFamily, ModelFamily]],
        {category: tuple(families) for category, families in contenders.items()},
    )


def _family_configs(config_root: Path) -> dict[ModelFamily, dict[str, JsonValue]]:
    configs: dict[ModelFamily, dict[str, JsonValue]] = {}
    for family in ("patchcore", "efficient_ad", "dinomaly"):
        config = load_model_config(config_root / f"{family}.yaml")
        configs[family] = cast(
            dict[str, JsonValue],
            config.model_dump(mode="json", exclude_computed_fields=True),
        )
    return configs


def build_stage(
    *,
    name: str,
    config_root: Path,
    manifest: DatasetManifest,
    contenders_path: Path | None,
) -> ExperimentStage:
    contenders = None
    if name == "replication":
        if contenders_path is None:
            raise ValueError("replication stage requires --contenders")
        contenders = _load_contenders(
            contenders_path, dataset_manifest_sha256=manifest.identity
        )
    return ExperimentStage.model_validate(
        {
            "name": name,
            "family_configs": _family_configs(config_root),
            "dataset_manifest_sha256": manifest.identity,
            "contenders": contenders,
        }
    )


def _manifest_images(
    root: Path,
    manifest: DatasetManifest,
    *,
    prefix: str,
    exclude_ground_truth: bool = False,
) -> tuple[Path, ...]:
    relative_paths = sorted(
        item.relative_path
        for item in manifest.files
        if item.relative_path.startswith(prefix)
        and Path(item.relative_path).suffix.lower() == ".png"
        and (not exclude_ground_truth or "ground_truth" not in Path(item.relative_path).parts)
    )
    if not relative_paths:
        raise ValueError(f"manifest contains no images below {prefix}")
    return tuple((root / relative).resolve(strict=True) for relative in relative_paths)


def _load_run_spec(path: Path) -> RunSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("run spec root must be an object")
    canonical = payload.pop("canonical_sha256", None)
    spec = RunSpec.model_validate(cast(dict[str, Any], payload))
    if canonical != spec.identity:
        raise ValueError("run spec canonical identity mismatch")
    return spec


def _verified_fit_artifact(
    path: Path, *, spec: RunSpec, config: ModelConfig
) -> FitArtifact | None:
    if not path.is_file():
        return None
    artifact = FitArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    if (
        artifact.family != spec.model_family
        or artifact.category != spec.category
        or artifact.seed != spec.seed
        or artifact.config_sha256 != config.identity
        or not artifact.checkpoint.path.is_file()
        or sha256_file(artifact.checkpoint.path) != artifact.checkpoint.sha256
    ):
        raise ValueError("existing fit artifact is incompatible or corrupt")
    return artifact


def _verified_prediction_artifact(
    path: Path,
    *,
    spec: RunSpec,
    config: ModelConfig,
    split: str,
) -> PredictionArtifact | None:
    if not path.is_file():
        return None
    artifact = PredictionArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    if (
        artifact.family != spec.model_family
        or artifact.category != spec.category
        or artifact.split != split
        or artifact.config_sha256 != config.identity
    ):
        raise ValueError("existing prediction artifact is incompatible")
    for item in artifact.anomaly_maps:
        if not item.path.is_file() or sha256_file(item.path) != item.sha256:
            raise ValueError("existing prediction anomaly map is corrupt")
    return artifact


def _predict_or_reuse(
    *,
    adapter: AnomalyExperimentAdapter,
    spec: RunSpec,
    config: ModelConfig,
    checkpoint: Path,
    images: tuple[Path, ...],
    split: str,
    predictions_root: Path,
    device: str,
    auxiliary_roots: Mapping[str, Path],
) -> PredictionArtifact:
    artifact_path = predictions_root / f"{split}.json"
    existing = _verified_prediction_artifact(
        artifact_path, spec=spec, config=config, split=split
    )
    if existing is not None:
        return existing
    output_dir = predictions_root / f"{split}-maps"
    if output_dir.exists():
        quarantine = output_dir.with_name(f"{output_dir.name}.incomplete-{time.time_ns()}")
        os.replace(output_dir, quarantine)
    expected_shape = config.preprocessing.center_crop or config.input_size
    artifact = adapter.predict(
        PredictContext(
            category=spec.category,
            images=images,
            split=cast(PredictionSplit, split),
            output_dir=output_dir,
            model_bundle_id=f"run:{spec.identity}",
            device=device,
            expected_map_shapes=tuple(expected_shape for _ in images),
            checkpoint_path=checkpoint,
            auxiliary_data_roots=auxiliary_roots,
        )
    )
    write_contract(artifact_path, artifact)
    return artifact


def _worker_artifacts(run_dir: Path, attempt_config: Path) -> dict[str, str]:
    roots = tuple(run_dir / name for name in ("checkpoints", "predictions", "metrics"))
    files = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    ]
    files.append(attempt_config)
    return {
        path.relative_to(run_dir).as_posix(): sha256_file(path)
        for path in sorted(files)
    }


def _classify_worker_error(error: BaseException) -> str:
    message = str(error).lower()
    if "out of memory" in message:
        return "oom"
    if "checksum" in message or "identity" in message or "hash" in message:
        return "checksum_mismatch"
    if "non-finite" in message or "nan" in message or "inf" in message:
        return "non_finite"
    if "shape" in message:
        return "invalid_shape"
    if "checkpoint" in message:
        return "corrupt_checkpoint"
    return "subprocess"


def execute_worker(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.expanduser().resolve(strict=True)
    result_path = run_dir / "worker-result.json"
    started = time.perf_counter()
    try:
        spec = _load_run_spec(args.spec.expanduser().resolve(strict=True))
        config_payload = json.loads(args.attempt_config.read_text(encoding="utf-8"))
        config = ModelConfig.model_validate(config_payload)
        if config.family != spec.model_family:
            raise ValueError("attempt config family differs from run specification")
        manifest = load_dataset_manifest(args.dataset_manifest)
        if manifest.identity != spec.dataset_manifest_sha256:
            raise ValueError("run specification dataset identity mismatch")
        data_root = args.data_root.expanduser().resolve(strict=True)
        auxiliary_roots: dict[str, Path] = {}
        if args.imagenette_root is not None:
            auxiliary_roots["imagenette"] = args.imagenette_root.expanduser().resolve(strict=True)

        peak_vram_mib: float | None = None
        try:
            torch_module: Any | None = importlib.import_module("torch")
        except ImportError:
            torch_module = None
        if (
            torch_module is not None
            and args.device.startswith("cuda")
            and torch_module.cuda.is_available()
        ):
            torch_module.cuda.reset_peak_memory_stats()

        adapter = create_adapter(spec.model_family, config)
        fit_artifact_path = run_dir / "checkpoints" / "fit-artifact.json"
        fit_artifact = _verified_fit_artifact(
            fit_artifact_path, spec=spec, config=config
        )
        if fit_artifact is None:
            attempt_root = args.attempt_config.parent
            fit_dir = attempt_root / "fit"
            if fit_dir.exists():
                os.replace(fit_dir, fit_dir.with_name(f"fit.incomplete-{time.time_ns()}"))
            train_images = _manifest_images(
                data_root,
                manifest,
                prefix=f"{spec.category}/train/good/",
            )
            trained = adapter.fit(
                FitContext(
                    category=spec.category,
                    images=train_images,
                    dataset_root=data_root,
                    dataset_manifest=manifest,
                    seed=spec.seed,
                    output_dir=fit_dir,
                    device=args.device,
                    auxiliary_data_roots=auxiliary_roots,
                    resume_checkpoint=args.resume_checkpoint,
                )
            )
            checkpoint = run_dir / "checkpoints" / "model.ckpt"
            if checkpoint.exists():
                raise ValueError("unregistered final checkpoint already exists")
            shutil.move(str(trained.checkpoint.path), checkpoint)
            fit_artifact = trained.model_copy(
                update={
                    "checkpoint": ArtifactFile(
                        path=checkpoint,
                        sha256=sha256_file(checkpoint),
                        size=checkpoint.stat().st_size,
                    )
                }
            )
            write_contract(fit_artifact_path, fit_artifact)
        checkpoint = fit_artifact.checkpoint.path

        validation = _predict_or_reuse(
            adapter=adapter,
            spec=spec,
            config=config,
            checkpoint=checkpoint,
            images=_manifest_images(
                data_root,
                manifest,
                prefix=f"{spec.category}/validation/good/",
            ),
            split="validation",
            predictions_root=run_dir / "predictions",
            device=args.device,
            auxiliary_roots=auxiliary_roots,
        )
        public = _predict_or_reuse(
            adapter=adapter,
            spec=spec,
            config=config,
            checkpoint=checkpoint,
            images=_manifest_images(
                data_root,
                manifest,
                prefix=f"{spec.category}/test_public/",
                exclude_ground_truth=True,
            ),
            split="test_public",
            predictions_root=run_dir / "predictions",
            device=args.device,
            auxiliary_roots=auxiliary_roots,
        )
        scores = np.asarray(
            [record.anomaly_score for record in validation.records], dtype=np.float64
        )
        threshold = conformal_upper_threshold(scores)
        threshold_path = run_dir / "metrics" / "threshold.json"
        if threshold_path.exists():
            existing_threshold = ThresholdResult.model_validate_json(
                threshold_path.read_text(encoding="utf-8")
            )
            if existing_threshold != threshold:
                raise ValueError("existing threshold artifact identity mismatch")
        else:
            write_contract(threshold_path, threshold)

        output_path = run_dir / "metrics" / "run-output.json"
        output_payload = {
            "schema_version": "1.0.0",
            "run_identity": spec.identity,
            "fit_artifact_sha256": sha256_file(fit_artifact_path),
            "validation_artifact_sha256": sha256_file(
                run_dir / "predictions" / "validation.json"
            ),
            "public_artifact_sha256": sha256_file(
                run_dir / "predictions" / "test_public.json"
            ),
            "threshold_artifact_sha256": sha256_file(threshold_path),
            "validation_count": len(validation.records),
            "public_count": len(public.records),
        }
        if output_path.exists():
            if json.loads(output_path.read_text(encoding="utf-8")) != output_payload:
                raise ValueError("existing run output identity mismatch")
        else:
            _write_atomic_json(output_path, output_payload)

        if (
            torch_module is not None
            and args.device.startswith("cuda")
            and torch_module.cuda.is_available()
        ):
            peak_vram_mib = float(torch_module.cuda.max_memory_allocated() / 1024**2)
        result = ExecutionResult(
            exit_code=0,
            artifacts=_worker_artifacts(run_dir, args.attempt_config),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            peak_vram_mib=peak_vram_mib,
        )
    except BaseException as error:
        result = ExecutionResult(
            exit_code=1,
            error_kind=cast(FailureKind, _classify_worker_error(error)),
            message=f"{error.__class__.__name__}: {error}",
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
    _write_atomic_json(result_path, asdict(result))
    return result.exit_code


def _attempt_command_factory(
    *,
    data_root: Path,
    dataset_manifest: Path,
    device: str,
    imagenette_root: Path | None,
) -> Callable[[RunRequest], Sequence[str]]:
    def command(request: RunRequest) -> Sequence[str]:
        attempt_dir = request.run_dir / "attempts" / f"attempt-{request.attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        config_path = attempt_dir / "config.json"
        config_payload = cast(dict[str, Any], request.effective_config)
        if config_path.exists():
            if json.loads(config_path.read_text(encoding="utf-8")) != config_payload:
                raise ValueError("existing attempt config differs from requested config")
        else:
            _write_atomic_json(config_path, config_payload)
        parts = [
            sys.executable,
            "-m",
            "experiments.run_matrix",
            "worker",
            "--spec",
            str(request.run_dir / "spec.json"),
            "--attempt-config",
            str(config_path),
            "--data-root",
            str(data_root),
            "--dataset-manifest",
            str(dataset_manifest),
            "--run-dir",
            str(request.run_dir),
            "--device",
            device,
        ]
        if request.resume_checkpoint is not None:
            parts.extend(("--resume-checkpoint", str(request.resume_checkpoint)))
        if imagenette_root is not None:
            parts.extend(("--imagenette-root", str(imagenette_root)))
        return parts

    return command


def _git_revision(repository: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("formal run matrix requires a clean Git worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the frozen MVTec AD 2 experiment matrix")
    parser.add_argument("--stage", required=True, choices=("screening", "replication"))
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--contenders", type=Path)
    parser.add_argument("--config-root", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--imagenette-root", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--gpu-lock", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def build_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Internal isolated run-matrix worker")
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--attempt-config", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--device", required=True)
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--imagenette-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "worker":
        return execute_worker(build_worker_parser().parse_args(values[1:]))

    args = build_parser().parse_args(values)
    repository = Path.cwd().resolve()
    data_root = args.data_root.expanduser().resolve(strict=True)
    runs_root = args.runs_root.expanduser().resolve()
    if runs_root == repository or runs_root.is_relative_to(repository):
        raise ValueError("runs root must be outside the repository working tree")
    manifest_path = (
        args.dataset_manifest.expanduser().resolve(strict=True)
        if args.dataset_manifest is not None
        else data_root.parent / f"{data_root.name}.manifest.json"
    )
    manifest = load_dataset_manifest(manifest_path)
    stage = build_stage(
        name=args.stage,
        config_root=args.config_root.expanduser().resolve(strict=True),
        manifest=manifest,
        contenders_path=args.contenders,
    )
    queue = expand_stage(stage)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "count": len(queue),
                    "identities": [item.identity for item in queue],
                    "stage": stage.name,
                },
                sort_keys=True,
            )
        )
        return 0

    code_revision = _git_revision(repository)
    environment_lock_sha256 = sha256_file(repository / "uv.lock")
    lock_path = (
        args.gpu_lock.expanduser().resolve()
        if args.gpu_lock is not None
        else runs_root.parent / ".mvtec-ad2-gpu.lock"
    )
    repository_identity = hashlib.sha256(str(repository).encode("utf-8")).hexdigest()
    run_store = RunStore(runs_root)
    _freeze_queue(
        run_store.root,
        stage=stage,
        queue=queue,
        code_revision=code_revision,
    )
    runner = SubprocessExecutor(
        _attempt_command_factory(
            data_root=data_root,
            dataset_manifest=manifest_path,
            device=args.device,
            imagenette_root=args.imagenette_root,
        )
    )
    summary = Supervisor(
        run_store,
        runner=runner,
        gpu_lease=GpuLease(lock_path, repository_identity=repository_identity),
        code_revision=code_revision,
        environment_lock_sha256=environment_lock_sha256,
        model_revision=lambda spec: (
            f"anomalib:{spec.config.get('anomalib_version')}/"
            f"{spec.config.get('model_name')}/{spec.config.get('backbone')}"
        ),
    ).run(queue)
    print(json.dumps(asdict(summary), ensure_ascii=False, sort_keys=True))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
