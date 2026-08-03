from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from experiments.data.download import MVTECAD2_SOURCE, download_archive
from experiments.data.extract import extract_archive
from experiments.data.manifest import build_dataset_manifest


def _write_manifest(root: Path) -> Path:
    manifest = build_dataset_manifest(root)
    output = root.parent / f"{root.name}.manifest.json"
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    payload = manifest.model_dump(mode="json", exclude_computed_fields=True)
    payload["canonical_sha256"] = manifest.identity
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output)
    return output


def prepare(root: Path) -> Path:
    """Acquire or preserve, validate, and inventory an external dataset root."""

    root = root.expanduser().resolve()
    working_tree = Path.cwd().resolve()
    if root == working_tree or root.is_relative_to(working_tree):
        raise ValueError("dataset root must be outside the repository working tree")

    archive = root.parent / "mvtec_ad_2.tar.gz"
    download_archive(MVTECAD2_SOURCE, archive)
    if not root.exists():
        extract_archive(archive, root)
    return _write_manifest(root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the verified MVTec AD 2 dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare", help="download, extract, and inventory")
    prepare_parser.add_argument("--root", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        manifest_path = prepare(args.root)
        print(json.dumps({"status": "verified", "manifest": str(manifest_path)}))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
