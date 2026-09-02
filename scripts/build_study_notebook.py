"""Generate the committed Colab notebook for the cloud high-resolution study."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

NOTEBOOK_PATH = Path("notebooks/colab_high_resolution_patchcore.ipynb")

DATASET_MANIFEST_SHA256 = "557fd46fcfaa1c2618be315bced7f9f0ba381d8f45119929a200a9d12d1895bf"
MINIMUM_VRAM_MIB = 60000
STAGED_PNG_COUNTS = {"can": 710, "wallplugs": 566}
_STAGED_COUNTS_LITERAL = json.dumps(STAGED_PNG_COUNTS)

_INTRO = """# Cloud high-resolution PatchCore study

Completes the pre-registered study `patchcore-512-vs-768-can-wallplugs-seed42`, which exhausted a
24 GiB RTX 4090 during coreset fitting. The study code is unmodified; only the GPU changes.

Scope is `test_public` only. This notebook does not read private predictions, retrain a champion,
change a threshold, submit to the official server, publish, deploy, or tag. Any verdict, including
another resource limit, is a publishable outcome.

Run the cells in order. Three gates stop the notebook early if a precondition fails.
"""

_SETUP = f"""import json
import pathlib
import shutil
import subprocess
import sys

STAGE = pathlib.Path("/content/drive/MyDrive/mvtec-ad2-colab")
DATA = pathlib.Path("/content/data/mvtec-ad-2")
MANIFEST = pathlib.Path("/content/dataset-manifest.json")
REPO = pathlib.Path("/content/mvtec-ad2-inspection-platform")
RUNS = pathlib.Path("/content/runs")
GPU_LOCK = pathlib.Path("/content/mvtec-ad2-gpu.lock")
STUDY_REPORT = RUNS / "evidence" / "high-resolution-patchcore.json"
SIDECAR = pathlib.Path("/content/high_resolution_patchcore_cloud_environment.json")
REF = "main"
MINIMUM_VRAM_MIB = {MINIMUM_VRAM_MIB}
FROZEN_MANIFEST_SHA256 = "{DATASET_MANIFEST_SHA256}"
print("paths configured")
"""

_GATE_GPU = """probe = subprocess.run(
    [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ],
    text=True,
    capture_output=True,
    check=True,
)
query = probe.stdout.strip().splitlines()[0]
name, total_mib, driver = (part.strip() for part in query.split(",", maxsplit=2))
print(name, total_mib, "MiB", driver)
assert int(total_mib) >= MINIMUM_VRAM_MIB, (
    f"gate 1 failed: need >= {MINIMUM_VRAM_MIB} MiB, got {total_mib}. "
    "Reconnect to an 80 GB A100, an H100, or the 96 GB Blackwell runtime."
)
print("gate 1 passed: VRAM is sufficient for the 768 x 768 can fit")
"""

_MOUNT = """from google.colab import drive

drive.mount("/content/drive")

for name in ("can-public.tar", "wallplugs-public.tar", "dataset-manifest.json"):
    assert (STAGE / name).is_file(), f"missing staged input: {name}"

shutil.copy2(STAGE / "dataset-manifest.json", MANIFEST)
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
assert manifest["canonical_sha256"] == FROZEN_MANIFEST_SHA256, (
    "staged dataset manifest is not the frozen manifest"
)
print("staged inputs verified against the frozen dataset manifest")
"""

_EXTRACT = f"""DATA.mkdir(parents=True, exist_ok=True)
for archive in ("can-public.tar", "wallplugs-public.tar"):
    subprocess.run(["tar", "-x", "-f", str(STAGE / archive), "-C", str(DATA)], check=True)

for category, expected in {_STAGED_COUNTS_LITERAL}.items():
    found = len(list((DATA / category).rglob("*.png")))
    assert found == expected, f"{{category}}: expected {{expected}} PNG files, found {{found}}"
    assert not (DATA / category / "test_private").exists(), "private split must not be staged"
print("dataset extracted with the expected public split counts")
"""

_CLONE = """if not REPO.exists():
    subprocess.run(
        [
            "git",
            "clone",
            "https://github.com/kuotunyu/mvtec-ad2-inspection-platform.git",
            str(REPO),
        ],
        check=True,
    )
subprocess.run(["git", "-C", str(REPO), "fetch", "--all", "--tags"], check=True)
subprocess.run(["git", "-C", str(REPO), "checkout", "--detach", REF], check=True)

status = subprocess.run(
    ["git", "-C", str(REPO), "status", "--porcelain"],
    text=True,
    capture_output=True,
    check=True,
).stdout
assert status.strip() == "", f"gate 2 failed: worktree is not clean\\n{status}"

head = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "HEAD"],
    text=True,
    capture_output=True,
    check=True,
).stdout.strip()
print("gate 2 passed: clean worktree at", head)
"""

_SYNC = """subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv==0.11.18"], check=True)
subprocess.run(["uv", "sync", "--frozen", "--extra", "ml"], cwd=REPO, check=True)
print("environment synchronized from the committed lockfile")
"""

_GATE_TORCH = """probe = subprocess.run(
    [
        "uv",
        "run",
        "python",
        "-c",
        "import torch;"
        "print(torch.__version__, torch.version.cuda, torch.cuda.is_available(),"
        " torch.cuda.get_device_name(0))",
    ],
    cwd=REPO,
    text=True,
    capture_output=True,
    check=True,
).stdout.strip()
print(probe)
assert "True" in probe, "gate 3 failed: torch cannot see the GPU"
print("gate 3 passed: torch verified in a subprocess, kernel holds no CUDA context")
"""

_COMMAND = """COMMAND = [
    "uv",
    "run",
    "python",
    "-m",
    "experiments.high_resolution_patchcore",
    "--data-root",
    str(DATA),
    "--dataset-manifest",
    str(MANIFEST),
    "--runs-root",
    str(RUNS),
    "--candidate-config",
    "experiments/configs/research/patchcore-768.yaml",
    "--gpu-lock",
    str(GPU_LOCK),
]
dry = subprocess.run([*COMMAND, "--dry-run"], cwd=REPO, text=True, capture_output=True, check=True)
print(dry.stdout.strip())
print("dry run resolved both run identities without acquiring the GPU")
"""

_RUN = """LOG = pathlib.Path("/content/study.log")
with LOG.open("w", encoding="utf-8") as stream:
    process = subprocess.Popen(
        COMMAND,
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        stream.write(line)
        print(line, end="")
    exit_code = process.wait()
print("study exited", exit_code)
"""

_SYNC_RUNS = """DRIVE_RUNS = STAGE / "runs"
if RUNS.exists():
    shutil.copytree(RUNS, DRIVE_RUNS, dirs_exist_ok=True)
    print("runs root synchronized to Drive")
else:
    print("no runs root to synchronize")
"""

_CAPTURE = """
assert STUDY_REPORT.is_file(), "study did not produce a report; inspect /content/study.log"
subprocess.run(
    [
        "uv",
        "run",
        "python",
        "scripts/capture_study_environment.py",
        "--study-report",
        str(STUDY_REPORT),
        "--runs-root",
        str(RUNS),
        "--output",
        str(SIDECAR),
    ],
    cwd=REPO,
    check=True,
)
print("hardware provenance captured")
"""

_DELIVER = """RESULTS = STAGE / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
shutil.copy2(STUDY_REPORT, RESULTS / "high_resolution_patchcore_cloud.json")
shutil.copy2(SIDECAR, RESULTS / "high_resolution_patchcore_cloud_environment.json")

for name in (
    "high_resolution_patchcore_cloud.json",
    "high_resolution_patchcore_cloud_environment.json",
):
    print("=" * 8, name)
    print((RESULTS / name).read_text(encoding="utf-8"))
print("both artifacts written to", RESULTS)
"""

_CELLS: tuple[tuple[str, str], ...] = (
    ("markdown", _INTRO),
    ("code", _SETUP),
    ("code", _GATE_GPU),
    ("code", _MOUNT),
    ("code", _EXTRACT),
    ("code", _CLONE),
    ("code", _SYNC),
    ("code", _GATE_TORCH),
    ("code", _COMMAND),
    ("code", _RUN),
    ("code", _SYNC_RUNS),
    ("code", _CAPTURE),
    ("code", _DELIVER),
)


def _source_lines(body: str) -> list[str]:
    lines = body.strip("\n").splitlines()
    return [f"{line}\n" for line in lines[:-1]] + [lines[-1]]


def build_notebook() -> dict[str, Any]:
    """Build the deterministic notebook payload."""

    cells: list[dict[str, Any]] = []
    for cell_type, body in _CELLS:
        cell: dict[str, Any] = {
            "cell_type": cell_type,
            "metadata": {},
            "source": _source_lines(body),
        }
        if cell_type == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.append(cell)
    return {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


def render(payload: dict[str, Any]) -> str:
    """Return the canonical notebook text for the given payload."""

    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the cloud study Colab notebook")
    parser.add_argument("--output", type=Path, default=NOTEBOOK_PATH)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    text = render(build_notebook())
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != text:
            print("notebook is stale; rerun without --check")
            return 1
        print("notebook matches its generator")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, args.output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    print("notebook written to", args.output.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
