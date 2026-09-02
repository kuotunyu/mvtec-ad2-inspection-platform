"""Capture sanitized hardware provenance for one completed research study."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
EVALUATION_SCOPE = "test_public-only"

_NVIDIA_SMI_TIMEOUT_SECONDS = 15
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PRIVATE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/home/|/Users/|\\Users\\|/content/|/mnt/|/root/)",
    re.IGNORECASE,
)

GpuProbe = Callable[[], tuple[str, str, int]]
VersionProbe = Callable[[], dict[str, str]]


def probe_gpu() -> tuple[str, str, int]:
    """Return the GPU name, driver version, and total memory in MiB."""

    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        capture_output=True,
        check=True,
        timeout=_NVIDIA_SMI_TIMEOUT_SECONDS,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("nvidia-smi reported no GPU")
    name, driver, memory = (part.strip() for part in lines[0].split(",", maxsplit=2))
    return name, driver, int(memory)


def probe_versions() -> dict[str, str]:
    """Return the pinned runtime versions, importing torch lazily."""

    import torch

    return {
        "anomalib": importlib.metadata.version("anomalib"),
        "cuda_runtime": str(torch.version.cuda),
        "platform": platform.system(),
        "python": platform.python_version(),
        "torch": str(torch.__version__),
    }


def build_environment(
    *,
    gpu: GpuProbe = probe_gpu,
    versions: VersionProbe = probe_versions,
) -> dict[str, Any]:
    """Assemble the environment block using the serving-benchmark field names."""

    name, driver, memory_mib = gpu()
    if not name or not driver or memory_mib <= 0:
        raise ValueError("GPU probe returned an incomplete identity")
    return {
        "gpu_driver": driver,
        "gpu_memory_mib": memory_mib,
        "gpu_name": name,
        **versions(),
    }


def candidate_run_identities(report: Mapping[str, Any]) -> dict[str, str]:
    """Map each study category to the candidate run identity recorded for it."""

    identities: dict[str, str] = {}
    for group in ("comparisons", "failures"):
        for item in report.get(group) or ():
            category = str(item["category"])
            if category in identities:
                raise ValueError(f"study report records {category} more than once")
            identities[category] = str(item["candidate_run_identity"])
    if not identities:
        raise ValueError("study report records no candidate run identity")
    return identities


def training_peaks(runs_root: Path, identities: Mapping[str, str]) -> dict[str, float]:
    """Read each candidate run's recorded training peak VRAM in MiB."""

    peaks: dict[str, float] = {}
    for category, identity in sorted(identities.items()):
        record = json.loads((runs_root / identity / "record.json").read_text(encoding="utf-8"))
        peak = record.get("peak_vram_mib")
        if isinstance(peak, bool) or not isinstance(peak, int | float) or peak <= 0:
            raise ValueError(f"run record for {category} lacks a positive peak_vram_mib")
        peaks[category] = float(peak)
    return peaks


def build_sidecar(
    *,
    report: Mapping[str, Any],
    runs_root: Path,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the sanitized sidecar payload for one completed study report."""

    identity = report.get("canonical_sha256")
    if not isinstance(identity, str) or _SHA256.fullmatch(identity) is None:
        raise ValueError("study report lacks a canonical_sha256 digest")
    if report.get("scope") != EVALUATION_SCOPE or report.get("submitted") is not False:
        raise ValueError("study report is not an unsubmitted public-only result")
    payload: dict[str, Any] = {
        "environment": dict(environment),
        "evaluation_scope": EVALUATION_SCOPE,
        "schema_version": SCHEMA_VERSION,
        "study": str(report["study"]),
        "study_report_sha256": identity,
        "submitted": False,
        "training_peak_vram_mib": training_peaks(runs_root, candidate_run_identities(report)),
        "verdict": str(report["verdict"]),
    }
    match = _PRIVATE.search(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if match is not None:
        raise ValueError(f"sidecar payload contains a private path fragment: {match.group(0)!r}")
    return payload


def write_sidecar(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write the sidecar atomically without silently replacing different content."""

    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if json.loads(destination.read_text(encoding="utf-8")) != payload:
            raise ValueError("existing study environment sidecar differs")
        return destination
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(dict(payload), stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture sanitized hardware provenance for a completed research study"
    )
    parser.add_argument("--study-report", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = args.study_report.expanduser().resolve(strict=True)
    payload = build_sidecar(
        report=json.loads(report_path.read_text(encoding="utf-8")),
        runs_root=args.runs_root.expanduser().resolve(strict=True),
        environment=build_environment(),
    )
    destination = write_sidecar(args.output, payload)
    print(
        json.dumps(
            {"output": destination.name, "verdict": payload["verdict"]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
