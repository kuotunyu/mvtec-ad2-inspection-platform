from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from scripts.security_scan import scan_root
from scripts.verify_claims import extract_claims, verify_claims
from scripts.verify_public_boundary import verify_paths


@dataclass(frozen=True)
class ReleaseFinding:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ReleaseVerificationReport:
    ok: bool
    source: str
    checked_files: int
    findings: tuple[ReleaseFinding, ...]


_SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "coverage",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
}
_PRIVATE_PARTS = {"artifacts", "checkpoints", "data", "runtime", "runs", "uploads"}
_PRIVATE_SUFFIXES = {
    ".ckpt",
    ".db",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
}
_OPENAPI_HASH = re.compile(r"^// openapi-source-sha256: ([0-9a-f]{64})$", re.MULTILINE)
_MUTABLE_MODEL = re.compile(
    r"(?:model(?:_reference|_revision|_version)?|revision|checkpoint)"
    r"[\"']?\s*[:=]\s*[\"']?(?:latest|main|master|nightly)[\"']?",
    re.IGNORECASE,
)


def _files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in _SKIP_PARTS for part in path.relative_to(root).parts)
    )


def _finding(code: str, path: Path | str, message: str) -> ReleaseFinding:
    rendered = path.as_posix() if isinstance(path, Path) else path
    return ReleaseFinding(code, rendered, message)


def _verify_openapi(root: Path) -> list[ReleaseFinding]:
    schema = root / "apps/web/openapi.json"
    generated = root / "apps/web/src/api/generated.ts"
    if not schema.is_file() and not generated.is_file():
        return []
    if not schema.is_file() or not generated.is_file():
        return [_finding("stale_openapi_client", "apps/web", "OpenAPI inputs are incomplete")]
    match = _OPENAPI_HASH.search(generated.read_text(encoding="utf-8"))
    canonical_schema = schema.read_bytes().replace(b"\r\n", b"\n")
    actual = hashlib.sha256(canonical_schema).hexdigest()
    if match is None or match.group(1) != actual:
        return [
            _finding(
                "stale_openapi_client",
                generated.relative_to(root),
                "generated client is not bound to the current OpenAPI schema",
            )
        ]
    return []


def _verify_generated_assets(root: Path) -> list[ReleaseFinding]:
    manifest = root / "docs/assets/manifest.json"
    if not manifest.is_file():
        return []
    try:
        assets = json.loads(manifest.read_text(encoding="utf-8"))["assets"]
        stale = [
            name
            for name, expected in assets.items()
            if not (root / "docs/assets" / name).is_file()
            or hashlib.sha256((root / "docs/assets" / name).read_bytes()).hexdigest() != expected
        ]
    except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
        stale = ["manifest.json"]
    if not stale:
        return []
    return [
        _finding(
            "dirty_generated_assets",
            "docs/assets/manifest.json",
            "asset hashes do not match: " + ", ".join(sorted(stale)),
        )
    ]


def _verify_numeric_claims(root: Path) -> list[ReleaseFinding]:
    documents = [
        path
        for relative in ("README.md", "docs/CASE_STUDY.md", "docs/MODEL_CARD.md")
        if (path := root / relative).is_file()
    ]
    if not documents:
        return []
    claims = extract_claims(documents)
    report = verify_claims(claims, root)
    if claims and report.ok:
        return []
    detail = "; ".join(report.errors) if report.errors else "no evidence-bound claims found"
    return [_finding("stale_numeric_claim", "README.md", detail)]


def _verify_model_references(root: Path, files: list[Path]) -> list[ReleaseFinding]:
    findings: list[ReleaseFinding] = []
    for path in files:
        if path.suffix.lower() not in {".json", ".toml", ".yaml", ".yml"}:
            continue
        if path.stat().st_size > 1024 * 1024:
            continue
        if _MUTABLE_MODEL.search(path.read_text(encoding="utf-8", errors="ignore")):
            findings.append(
                _finding(
                    "mutable_model_reference",
                    path.relative_to(root),
                    "model references must use an immutable version or digest",
                )
            )
    return findings


def verify_source(source: Path) -> ReleaseVerificationReport:
    root = source.resolve()
    files = _files(root)
    relative_files = [path.relative_to(root) for path in files]
    findings: list[ReleaseFinding] = []
    if not (root / "LICENSE").is_file():
        findings.append(_finding("missing_license", "LICENSE", "release requires a license"))
    for required in ("pyproject.toml", "uv.lock", "apps/web/package-lock.json"):
        if (root / required).parent.exists() and not (root / required).is_file():
            findings.append(
                _finding("missing_lockfile", required, "frozen dependency lock is missing")
            )
    security = scan_root(root)
    remap = {"model_artifact": "private_artifact", "large_binary": "oversized_binary"}
    findings.extend(
        _finding(remap.get(item.code, item.code), item.path, item.message)
        for item in security.findings
    )
    boundary = verify_paths(root, relative_files)
    findings.extend(
        _finding(code, ".", "public source boundary verification failed")
        for code in boundary.error_codes
        if code not in {"private_artifact", "oversized_source_file"}
    )
    findings.extend(_verify_openapi(root))
    findings.extend(_verify_generated_assets(root))
    findings.extend(_verify_numeric_claims(root))
    findings.extend(_verify_model_references(root, files))
    unique = {(item.code, item.path, item.message): item for item in findings}
    ordered = tuple(sorted(unique.values(), key=lambda item: (item.path, item.code, item.message)))
    return ReleaseVerificationReport(not ordered, root.name, len(files), ordered)


def _archive_names(archive: Path) -> list[str]:
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive, "r:*") as handle:
            return [member.name for member in handle.getmembers()]
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as handle:
            return handle.namelist()
    raise ValueError(f"unsupported archive: {archive}")


def verify_archive(archive: Path) -> tuple[ReleaseFinding, ...]:
    findings: list[ReleaseFinding] = []
    names = _archive_names(archive)
    parsed = [PurePosixPath(name.replace("\\", "/")) for name in names]
    roots = {path.parts[0] for path in parsed if path.parts}
    strip_archive_root = len(roots) == 1
    for name, path in zip(names, parsed, strict=True):
        content_parts = path.parts[1:] if strip_archive_root else path.parts
        first_content = content_parts[0].lower() if content_parts else ""
        unsafe = path.is_absolute() or ".." in path.parts
        private = first_content in _PRIVATE_PARTS or path.suffix.lower() in _PRIVATE_SUFFIXES
        environment = any(part.startswith(".env") and part != ".env.example" for part in path.parts)
        if unsafe or private or environment:
            findings.append(
                _finding("forbidden_archive_entry", name, "archive contains non-release material")
            )
    return tuple(sorted(findings, key=lambda item: item.path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", action="append", type=Path, default=[])
    args = parser.parse_args()
    report = verify_source(args.source)
    archive_findings = tuple(item for archive in args.archive for item in verify_archive(archive))
    if archive_findings:
        report = ReleaseVerificationReport(
            False,
            report.source,
            report.checked_files,
            tuple((*report.findings, *archive_findings)),
        )
    payload = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
