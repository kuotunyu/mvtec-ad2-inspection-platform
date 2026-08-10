from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublicBoundaryReport:
    ok: bool
    checked_files: int
    error_codes: tuple[str, ...]


_FORBIDDEN_SUFFIXES = {
    ".ckpt",
    ".db",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
}
_PRIVATE_ROOTS = {"artifacts", "checkpoints", "data", "runtime", "runs", "uploads"}
_IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def _has_invalid_public_text(content: bytes) -> bool:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return "\ufffd" in text or any(unicodedata.category(character) == "Co" for character in text)


def _verify_entries(entries: dict[Path, bytes]) -> PublicBoundaryReport:
    errors: set[str] = set()
    manifested: dict[str, str] = {}
    manifest_path = Path("fixtures/public-demo/manifest.json")
    if manifest_path in entries:
        try:
            payload = json.loads(entries[manifest_path])
            manifested = {
                f"fixtures/public-demo/{item['filename']}": item["sha256"]
                for item in payload["fixtures"]
            }
        except (KeyError, TypeError, json.JSONDecodeError):
            errors.add("fixture_manifest")
    docs_manifest_path = Path("docs/assets/manifest.json")
    if docs_manifest_path in entries:
        try:
            payload = json.loads(entries[docs_manifest_path])
            manifested.update(
                {
                    f"docs/assets/{filename}": sha256
                    for filename, sha256 in payload["assets"].items()
                }
            )
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
            errors.add("docs_asset_manifest")
    for path, content in entries.items():
        relative = path.as_posix()
        top_level = path.parts[0].lower() if path.parts else ""
        if path.suffix.lower() in _FORBIDDEN_SUFFIXES:
            errors.add("private_artifact")
        if top_level in _PRIVATE_ROOTS:
            errors.add("private_root")
        if path.name.startswith(".env") and path.name != ".env.example":
            errors.add("environment_file")
        if path.suffix.lower() in _IMAGE_SUFFIXES:
            expected = manifested.get(relative)
            if expected is None:
                errors.add("unmanifested_image")
            elif hashlib.sha256(content).hexdigest() != expected:
                errors.add("fixture_hash")
        if path.suffix.lower() in _TEXT_SUFFIXES and _has_invalid_public_text(content):
            errors.add("invalid_public_text")
        if len(content) > 5 * 1024 * 1024:
            errors.add("oversized_source_file")
    return PublicBoundaryReport(not errors, len(entries), tuple(sorted(errors)))


def verify_paths(root: Path, paths: list[Path]) -> PublicBoundaryReport:
    entries = {path: (root / path).read_bytes() for path in paths if (root / path).is_file()}
    manifest = root / "fixtures/public-demo/manifest.json"
    if manifest.is_file() and Path("fixtures/public-demo/manifest.json") not in entries:
        entries[Path("fixtures/public-demo/manifest.json")] = manifest.read_bytes()
    docs_manifest = root / "docs/assets/manifest.json"
    if docs_manifest.is_file() and Path("docs/assets/manifest.json") not in entries:
        entries[Path("docs/assets/manifest.json")] = docs_manifest.read_bytes()
    return _verify_entries(entries)


def verify_git_tree(root: Path, tree: str) -> PublicBoundaryReport:
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "-z", tree],
        check=True,
        capture_output=True,
    ).stdout
    paths = [Path(item.decode("utf-8")) for item in listed.split(b"\0") if item]
    entries: dict[Path, bytes] = {}
    for path in paths:
        entries[path] = subprocess.run(
            ["git", "-C", str(root), "show", f"{tree}:{path.as_posix()}"],
            check=True,
            capture_output=True,
        ).stdout
    return _verify_entries(entries)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-tree", default="HEAD")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    report = verify_git_tree(args.root.resolve(), args.git_tree)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
