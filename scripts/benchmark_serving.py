from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]

from experiments.data.manifest import REQUIRED_CATEGORIES
from experiments.orchestration.gpu_lock import GpuLease
from inspection_platform.inference.anomalib_runtime import LoadedAnomalibModel
from inspection_platform.inference.runtime import InferenceRuntime
from inspection_platform.registry.repository import ModelRegistry
from scripts.gpu_product_smoke import (
    _input_for_category,
    _read_json,
    _write_json,
    verify_real_registry,
)

_PRIVATE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/home/|/Users/|\\Users\\|\.(?:png|jpe?g|tiff?|bmp)\b)",
    re.IGNORECASE,
)


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def summarize_samples(samples: list[float]) -> dict[str, Any]:
    if not samples or any(not math.isfinite(item) or item <= 0 for item in samples):
        raise ValueError("latency samples must be positive and finite")
    mean = statistics.fmean(samples)
    margin = 0.0
    if len(samples) > 1:
        margin = 1.96 * statistics.stdev(samples) / math.sqrt(len(samples))
    return {
        "mean_latency_ms": mean,
        "mean_latency_95ci_ms": [max(0.0, mean - margin), mean + margin],
        "p50_latency_ms": _percentile(samples, 0.50),
        "p95_latency_ms": _percentile(samples, 0.95),
        "throughput_images_per_second": 1000.0 / mean,
    }


def validate_serving_report(report: dict[str, Any]) -> tuple[str, ...]:
    errors: set[str] = set()
    if report.get("schema_version") != "1.0.0" or report.get("status") != "passed":
        errors.add("invalid_status")
    if not re.fullmatch(r"[0-9a-f]{40}", str(report.get("code_sha", ""))):
        errors.add("invalid_code_sha")
    categories = report.get("categories")
    if not isinstance(categories, dict) or set(categories) != set(REQUIRED_CATEGORIES):
        errors.add("invalid_categories")
    serialized = json.dumps(report, sort_keys=True)
    if _PRIVATE.search(serialized):
        errors.add("private_path_or_image")
    return tuple(sorted(errors))


def write_serving_evidence(output: Path, report: dict[str, Any]) -> None:
    errors = validate_serving_report(report)
    if errors:
        raise ValueError("invalid serving report: " + ", ".join(errors))
    _write_json(output, report)
    _write_json(
        output.parent / "manifest.json",
        {
            "schema_version": "1.0.0",
            "files": {output.name: hashlib.sha256(output.read_bytes()).hexdigest()},
        },
    )


def _sync(device: str) -> None:
    if device.startswith("cuda"):
        import torch

        torch.cuda.synchronize()


def _benchmark_worker(
    registry_root: Path,
    category: str,
    input_path: Path,
    output: Path,
    *,
    device: str,
    warmup: int,
    repetitions: int,
) -> None:
    import torch

    root = registry_root.expanduser().resolve(strict=True)
    manifest = ModelRegistry(root).register(root / "categories" / category / "manifest.json")
    image = input_path.expanduser().resolve(strict=True).read_bytes()
    process = psutil.Process()
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    _sync(device)
    started = time.perf_counter()
    loaded = InferenceRuntime.load(
        manifest,
        root,
        device=device,
        trust_verified_bundle=True,
    )
    _sync(device)
    cold_start_ms = (time.perf_counter() - started) * 1000
    if not isinstance(loaded, LoadedAnomalibModel):
        raise TypeError("benchmark did not load a real Anomalib model")
    for _ in range(warmup):
        loaded.predict_with_map(image, input_id="serving-benchmark")
    samples: list[float] = []
    for _ in range(repetitions):
        _sync(device)
        started = time.perf_counter()
        detailed = loaded.predict_with_map(image, input_id="serving-benchmark")
        _sync(device)
        samples.append((time.perf_counter() - started) * 1000)
        if detailed.record.category != category or detailed.anomaly_map.ndim != 2:
            raise ValueError("benchmark prediction contract failed")
    result: dict[str, Any] = {
        "cold_start_ms": cold_start_ms,
        "warmup_repetitions": warmup,
        "measured_repetitions": repetitions,
        "process_rss_mib": process.memory_info().rss / (1024 * 1024),
        **summarize_samples(samples),
    }
    if device.startswith("cuda"):
        result.update(
            {
                "peak_allocated_vram_mib": torch.cuda.max_memory_allocated() / (1024 * 1024),
                "peak_reserved_vram_mib": torch.cuda.max_memory_reserved() / (1024 * 1024),
            }
        )
    _write_json(output, result)


def _run_worker(
    registry_root: Path,
    data_root: Path,
    category: str,
    output: Path,
    *,
    device: str,
    warmup: int,
    repetitions: int,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--registry",
        str(registry_root),
        "--data-root",
        str(data_root),
        "--category",
        category,
        "--worker-output",
        str(output),
        "--device",
        device,
        "--warmup",
        str(warmup),
        "--repetitions",
        str(repetitions),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"benchmark worker failed for {category}/{device}: {completed.stderr[-2000:]}"
        )
    return _read_json(output)


def _environment() -> dict[str, Any]:
    import torch

    query = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    ).stdout.strip()
    name, driver, memory = (part.strip() for part in query.split(",", maxsplit=2))
    return {
        "gpu_name": name,
        "gpu_driver": driver,
        "gpu_memory_mib": int(memory),
        "cuda_runtime": torch.version.cuda,
        "torch": torch.__version__,
        "anomalib": importlib.metadata.version("anomalib"),
        "python": platform.python_version(),
        "platform": platform.system(),
    }


def run_serving_benchmark(
    registry_root: Path,
    data_root: Path,
    *,
    code_sha: str,
    gpu_lock: Path,
    warmup: int,
    repetitions: int,
    cpu_repetitions: int,
) -> dict[str, Any]:
    registry = registry_root.expanduser().resolve(strict=True)
    data = data_root.expanduser().resolve(strict=True)
    index = verify_real_registry(registry, code_sha=code_sha)
    categories: dict[str, Any] = {}
    with (
        GpuLease(gpu_lock, repository_identity=code_sha, ttl_seconds=300).acquire(
            "plan04-task7-serving-benchmark"
        ) as handle,
        tempfile.TemporaryDirectory(prefix="mvtec-ad2-serving-benchmark-") as temporary_text,
    ):
        temporary = Path(temporary_text)
        for category in REQUIRED_CATEGORIES:
            gpu = _run_worker(
                registry,
                data,
                category,
                temporary / f"{category}-gpu.json",
                device="cuda:0",
                warmup=warmup,
                repetitions=repetitions,
            )
            handle.heartbeat()
            cpu: dict[str, Any] | None
            try:
                cpu = _run_worker(
                    registry,
                    data,
                    category,
                    temporary / f"{category}-cpu.json",
                    device="cpu",
                    warmup=0,
                    repetitions=cpu_repetitions,
                )
            except RuntimeError:
                cpu = None
            categories[category] = {
                "family": index["categories"][category]["family"],
                "run_identity": index["categories"][category]["run_identity"],
                "bundle_identity": index["categories"][category]["bundle_identity"],
                "artifact_size_bytes": sum(
                    item.size
                    for item in ModelRegistry(registry)
                    .register(registry / "categories" / category / "manifest.json")
                    .files
                ),
                "gpu": gpu,
                "cpu": cpu,
            }
            handle.heartbeat()
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "passed",
        "evaluation_scope": "local-rtx-4090-serving-only",
        "code_sha": code_sha,
        "champions_sha256": index["champions_sha256"],
        "dataset_manifest_sha256": index["dataset_manifest_sha256"],
        "registry_sha256": index["canonical_sha256"],
        "environment": _environment(),
        "configuration": {
            "batch_size": 1,
            "warmup_repetitions": warmup,
            "gpu_repetitions": repetitions,
            "cpu_repetitions": cpu_repetitions,
            "timing_scope": "decode-preprocess-model-postprocess",
        },
        "categories": categories,
    }
    errors = validate_serving_report(report)
    if errors:
        raise ValueError("invalid serving report: " + ", ".join(errors))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark frozen product-serving bundles")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-output", type=Path)
    parser.add_argument("--category", choices=REQUIRED_CATEGORIES)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--cpu-repetitions", type=int, default=3)
    parser.add_argument("--gpu-lock", type=Path, required=True)
    parser.add_argument("--code-sha")
    args = parser.parse_args()
    data_root = args.data_root or Path(os.environ["MVTECAD2_DATA_ROOT"])
    if args.worker:
        if args.category is None or args.worker_output is None:
            parser.error("worker mode requires --category and --worker-output")
        _benchmark_worker(
            args.registry,
            args.category,
            _input_for_category(data_root, args.category),
            args.worker_output,
            device=args.device,
            warmup=args.warmup,
            repetitions=args.repetitions,
        )
        return 0
    if args.output is None:
        parser.error("--output is required")
    code_sha = args.code_sha or os.environ["SOURCE_REVISION"]
    report = run_serving_benchmark(
        args.registry,
        data_root,
        code_sha=code_sha,
        gpu_lock=args.gpu_lock,
        warmup=args.warmup,
        repetitions=args.repetitions,
        cpu_repetitions=args.cpu_repetitions,
    )
    write_serving_evidence(args.output, report)
    print(json.dumps({"status": "passed", "categories": len(report["categories"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
