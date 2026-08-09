from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import numpy as np
from PIL import Image

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.models import ExportContext, ModelConfig, create_adapter
from experiments.orchestration.gpu_lock import GpuLease
from inspection_platform.contracts import (
    BundleFile,
    canonical_hash,
    sha256_file,
)
from inspection_platform.inference.anomalib_runtime import LoadedAnomalibModel
from inspection_platform.inference.runtime import InferenceRuntime
from inspection_platform.registry.repository import ModelRegistry
from inspection_platform.reports.builder import build_report_json

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ChampionSource:
    category: str
    family: str
    run_identity: str
    checkpoint: Path
    config: ModelConfig
    threshold: float


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path.name}")
    return cast(dict[str, Any], payload)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def discover_champion_run_ids(champions_path: Path, runs_root: Path) -> dict[str, str]:
    champions = _read_json(champions_path.expanduser().resolve(strict=True))
    frozen = champions.get("champions")
    decisions = champions.get("decisions")
    if not isinstance(frozen, dict) or set(frozen) != set(REQUIRED_CATEGORIES):
        raise ValueError("champion map must contain all eight categories")
    if not isinstance(decisions, list):
        raise ValueError("champion decisions are missing")
    by_category = {item.get("category"): item for item in decisions if isinstance(item, dict)}
    resolved_runs = runs_root.expanduser().resolve(strict=True)
    selected: dict[str, str] = {}
    for category in REQUIRED_CATEGORIES:
        winner = frozen[category]
        decision = by_category.get(category)
        if not isinstance(decision, dict) or decision.get("decision", {}).get("winner") != winner:
            raise ValueError(f"champion decision mismatch: {category}")
        candidates = decision.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError(f"champion candidates are missing: {category}")
        winner_rows = [item for item in candidates if item.get("family") == winner]
        if len(winner_rows) != 1:
            raise ValueError(f"winner candidate is ambiguous: {category}")
        identities = winner_rows[0].get("run_identities")
        if not isinstance(identities, list) or len(identities) != 3:
            raise ValueError(f"winner must have three replication runs: {category}")
        seed_42: list[str] = []
        for identity in identities:
            if not isinstance(identity, str) or not _SHA256.fullmatch(identity):
                raise ValueError(f"invalid run identity: {category}")
            spec = _read_json(resolved_runs / identity / "spec.json")
            if (
                spec.get("canonical_sha256") != identity
                or spec.get("category") != category
                or spec.get("model_family") != winner
            ):
                raise ValueError(f"run specification drift: {category}")
            if spec.get("seed") == 42:
                seed_42.append(identity)
        if len(seed_42) != 1:
            raise ValueError(f"expected exactly one seed-42 champion run: {category}")
        selected[category] = seed_42[0]
    return selected


def load_champion_sources(evidence_root: Path, runs_root: Path) -> tuple[ChampionSource, ...]:
    evidence = evidence_root.expanduser().resolve(strict=True)
    runs = runs_root.expanduser().resolve(strict=True)
    identities = discover_champion_run_ids(evidence / "champions.json", runs)
    sources: list[ChampionSource] = []
    for category in REQUIRED_CATEGORIES:
        identity = identities[category]
        run = runs / identity
        spec = _read_json(run / "spec.json")
        record = _read_json(run / "record.json")
        fit = _read_json(run / "checkpoints" / "fit-artifact.json")
        threshold_payload = _read_json(run / "metrics" / "threshold.json")
        if record.get("status") != "completed" or record.get("exit_code") != 0:
            raise ValueError(f"champion run is not completed: {category}")
        if record.get("spec") != identity:
            raise ValueError(f"champion record identity drift: {category}")
        config = ModelConfig.model_validate(spec.get("config"))
        if config.family != spec.get("model_family"):
            raise ValueError(f"champion config family drift: {category}")
        if fit.get("seed") != 42 or fit.get("config_sha256") != config.identity:
            raise ValueError(f"champion fit provenance drift: {category}")
        checkpoint_data = fit.get("checkpoint")
        if not isinstance(checkpoint_data, dict):
            raise ValueError(f"champion checkpoint metadata missing: {category}")
        checkpoint = run / "checkpoints" / "model.ckpt"
        if (
            not checkpoint.is_file()
            or sha256_file(checkpoint) != checkpoint_data.get("sha256")
            or checkpoint.stat().st_size != checkpoint_data.get("size")
        ):
            raise ValueError(f"champion checkpoint integrity failed: {category}")
        threshold = float(threshold_payload["threshold"])
        if not np.isfinite(threshold):
            raise ValueError(f"champion threshold is non-finite: {category}")
        sources.append(
            ChampionSource(
                category=category,
                family=cast(str, spec["model_family"]),
                run_identity=identity,
                checkpoint=checkpoint,
                config=config,
                threshold=threshold,
            )
        )
    return tuple(sources)


def _registry_index(registry_root: Path) -> dict[str, Any]:
    return _read_json(registry_root / "registry.json")


def verify_real_registry(registry_root: Path, *, code_sha: str) -> dict[str, Any]:
    root = registry_root.expanduser().resolve(strict=True)
    index = _registry_index(root)
    if index.get("code_sha") != code_sha or set(index.get("categories", {})) != set(
        REQUIRED_CATEGORIES
    ):
        raise ValueError("registry identity is incompatible with the serving gate")
    registry = ModelRegistry(root)
    for category in REQUIRED_CATEGORIES:
        manifest_path = root / "categories" / category / "manifest.json"
        manifest = registry.register(manifest_path)
        row = index["categories"][category]
        if (
            manifest.category != category
            or manifest.runtime_kind != "anomalib"
            or manifest.identity != row.get("bundle_identity")
            or sha256_file(manifest_path) != row.get("manifest_sha256")
        ):
            raise ValueError(f"registry manifest drift: {category}")
    return index


def prepare_real_registry(
    evidence_root: Path,
    runs_root: Path,
    registry_root: Path,
    *,
    code_sha: str,
    device: str = "cuda:0",
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", code_sha):
        raise ValueError("code SHA must be a full Git commit identity")
    destination = registry_root.expanduser().resolve()
    if destination.exists():
        return verify_real_registry(destination, code_sha=code_sha)
    sources = load_champion_sources(evidence_root, runs_root)
    evidence = evidence_root.expanduser().resolve(strict=True)
    champions = _read_json(evidence / "champions.json")
    temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    if temporary.exists():
        raise FileExistsError(temporary)
    temporary.mkdir(parents=True)
    categories: dict[str, dict[str, object]] = {}
    try:
        for source in sources:
            category_root = temporary / "categories" / source.category
            adapter = create_adapter(source.family, source.config)
            exported = adapter.export_bundle(
                ExportContext(
                    category=cast(Any, source.category),
                    checkpoint_path=source.checkpoint,
                    output_dir=category_root,
                    threshold=source.threshold,
                    device=device,
                )
            )
            files = tuple(
                BundleFile(
                    path=f"categories/{source.category}/{item.path}",
                    sha256=item.sha256,
                    size=item.size,
                )
                for item in exported.files
            )
            manifest = exported.model_copy(update={"files": files})
            manifest_path = category_root / "manifest.json"
            _write_json(
                manifest_path,
                manifest.model_dump(mode="json", exclude_computed_fields=True),
            )
            categories[source.category] = {
                "bundle_identity": manifest.identity,
                "family": source.family,
                "manifest_sha256": sha256_file(manifest_path),
                "run_identity": source.run_identity,
            }
            try:
                import torch

                torch.cuda.empty_cache()
            except ImportError:
                pass
        index: dict[str, Any] = {
            "schema_version": "1.0.0",
            "code_sha": code_sha,
            "champions_sha256": champions["canonical_sha256"],
            "dataset_manifest_sha256": champions["dataset_manifest_sha256"],
            "categories": categories,
        }
        index["canonical_sha256"] = canonical_hash(index)
        _write_json(temporary / "registry.json", index)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return verify_real_registry(destination, code_sha=code_sha)


def _input_for_category(data_root: Path, category: str) -> Path:
    candidates = tuple(sorted((data_root / category / "test_public").rglob("*.png")))
    if not candidates:
        raise FileNotFoundError(f"no permitted public test input for category: {category}")
    return candidates[0].resolve(strict=True)


def _render_artifacts(image_bytes: bytes, anomaly_map: np.ndarray[Any, Any]) -> tuple[bytes, bytes]:
    values = np.asarray(anomaly_map, dtype=np.float32)
    low, high = float(values.min()), float(values.max())
    normalized = np.zeros_like(values) if high <= low else (values - low) / (high - low)
    grayscale = Image.fromarray(np.uint8(np.clip(normalized * 255, 0, 255)), mode="L")
    source = Image.open(BytesIO(image_bytes)).convert("RGB")
    resized = grayscale.resize(source.size, Image.Resampling.BILINEAR)
    red = Image.new("RGB", source.size, (235, 55, 55))
    overlay = Image.composite(red, source, resized.point(lambda value: int(value * 0.55)))
    map_stream, overlay_stream = BytesIO(), BytesIO()
    grayscale.save(map_stream, format="PNG", optimize=False)
    overlay.save(overlay_stream, format="PNG", optimize=False)
    return map_stream.getvalue(), overlay_stream.getvalue()


def _smoke_worker(registry_root: Path, category: str, input_path: Path, output: Path) -> None:
    root = registry_root.expanduser().resolve(strict=True)
    manifest = ModelRegistry(root).register(root / "categories" / category / "manifest.json")
    loaded = InferenceRuntime.load(manifest, root, device="cuda:0")
    if not isinstance(loaded, LoadedAnomalibModel):
        raise TypeError("real serving gate did not load the Anomalib runtime")
    image_bytes = input_path.expanduser().resolve(strict=True).read_bytes()
    detailed = loaded.predict_with_map(image_bytes, input_id="serving-smoke")
    anomaly_png, overlay_png = _render_artifacts(image_bytes, detailed.anomaly_map)
    Image.open(BytesIO(anomaly_png)).verify()
    Image.open(BytesIO(overlay_png)).verify()
    report = build_report_json(
        {
            "schema_version": "1.0.0",
            "category": category,
            "model_bundle_id": detailed.record.model_bundle_id,
            "anomaly_score": detailed.record.anomaly_score,
            "anomaly_map_sha256": hashlib.sha256(anomaly_png).hexdigest(),
            "overlay_sha256": hashlib.sha256(overlay_png).hexdigest(),
        }
    )
    json.loads(report)
    result = {
        "status": "passed",
        "family": manifest.model_family,
        "bundle_identity": manifest.identity,
        "artifact_size_bytes": sum(item.size for item in manifest.files),
        "prediction_sha256": hashlib.sha256(detailed.record.model_dump_json().encode()).hexdigest(),
        "anomaly_map_sha256": hashlib.sha256(anomaly_png).hexdigest(),
        "overlay_sha256": hashlib.sha256(overlay_png).hexdigest(),
        "report_sha256": hashlib.sha256(report).hexdigest(),
    }
    _write_json(output, result)


def run_real_serving_gate(
    *,
    evidence_root: Path,
    runs_root: Path,
    data_root: Path,
    registry_root: Path,
    code_sha: str,
    gpu_lock: Path = Path("D:/.mvtec-ad2-gpu.lock"),
) -> dict[str, dict[str, Any]]:
    data = data_root.expanduser().resolve(strict=True)
    lease = GpuLease(gpu_lock, repository_identity=code_sha, ttl_seconds=300)
    results: dict[str, dict[str, Any]] = {}
    with lease.acquire("plan04-task7-product-smoke") as handle:
        index = prepare_real_registry(
            evidence_root,
            runs_root,
            registry_root,
            code_sha=code_sha,
        )
        handle.heartbeat()
        with tempfile.TemporaryDirectory(prefix="mvtec-ad2-serving-smoke-") as temporary_text:
            temporary = Path(temporary_text)
            for category in REQUIRED_CATEGORIES:
                output = temporary / f"{category}.json"
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker-smoke",
                    "--registry",
                    str(registry_root),
                    "--category",
                    category,
                    "--input",
                    str(_input_for_category(data, category)),
                    "--output",
                    str(output),
                ]
                completed = subprocess.run(command, text=True, capture_output=True, check=False)
                if completed.returncode != 0:
                    raise RuntimeError(
                        f"real serving worker failed for {category}: {completed.stderr[-2000:]}"
                    )
                results[category] = _read_json(output)
                if results[category].get("bundle_identity") != index["categories"][category].get(
                    "bundle_identity"
                ):
                    raise ValueError(f"smoke bundle identity drift: {category}")
                handle.heartbeat()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke frozen champions through product inference")
    parser.add_argument("--worker-smoke", action="store_true")
    parser.add_argument("--evidence-root", type=Path, default=Path("reports"))
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--gpu-lock", type=Path, default=Path("D:/.mvtec-ad2-gpu.lock"))
    parser.add_argument("--code-sha")
    parser.add_argument("--category", choices=REQUIRED_CATEGORIES)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker_smoke:
        if args.category is None or args.input is None or args.output is None:
            parser.error("worker mode requires --category, --input, and --output")
        _smoke_worker(args.registry, args.category, args.input, args.output)
        return 0
    runs_root = args.runs_root or Path(os.environ["MVTECAD2_RUNS_ROOT"])
    data_root = args.data_root or Path(os.environ["MVTECAD2_DATA_ROOT"])
    code_sha = args.code_sha or os.environ["SOURCE_REVISION"]
    results = run_real_serving_gate(
        evidence_root=args.evidence_root,
        runs_root=runs_root,
        data_root=data_root,
        registry_root=args.registry,
        code_sha=code_sha,
        gpu_lock=args.gpu_lock,
    )
    print(json.dumps({"status": "passed", "categories": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
