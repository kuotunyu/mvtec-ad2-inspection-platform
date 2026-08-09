from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class SecurityReport:
    ok: bool
    scanned_files: int
    findings: tuple[Finding, ...]


_SKIP_PARTS = {
    ".git",
    ".coverage",
    ".venv",
    ".codex-local",
    "node_modules",
    "coverage",
    "test-results",
    "playwright-report",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
_MODEL_SUFFIXES = {".ckpt", ".onnx", ".pt", ".pth", ".safetensors"}
_RUNTIME_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
_SECRET_PATTERNS = (
    re.compile(b"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[ps]_[A-Za-z0-9]{30,}"),
)
_ABSOLUTE_PATHS = (
    re.compile(rb"[A-Za-z]:\\Users\\[^\\\r\n]+"),
    re.compile(rb"/(?:Users|home)/[A-Za-z0-9._-]+/"),
)


def _files(root: Path) -> list[Path]:
    if (root / ".git").exists():
        listed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            check=True,
            capture_output=True,
        ).stdout
        return sorted(root / item.decode("utf-8") for item in listed.split(b"\0") if item)
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in _SKIP_PARTS for part in path.relative_to(root).parts)
    )


def scan_root(root: Path) -> SecurityReport:
    resolved = root.resolve()
    findings: list[Finding] = []
    files = _files(resolved)
    for path in files:
        relative = path.relative_to(resolved).as_posix()
        suffix = path.suffix.lower()
        if suffix in _MODEL_SUFFIXES:
            findings.append(
                Finding("model_artifact", relative, "model artifact is not public source")
            )
        if suffix in _RUNTIME_SUFFIXES:
            findings.append(
                Finding("runtime_database", relative, "runtime database is not public source")
            )
        if path.name.startswith(".env") and path.name != ".env.example":
            findings.append(
                Finding("environment_file", relative, "environment file is not public source")
            )
        if path.stat().st_size > 5 * 1024 * 1024:
            findings.append(
                Finding("large_binary", relative, "file exceeds the 5 MiB source boundary")
            )
        if path.stat().st_size > 10 * 1024 * 1024:
            continue
        content = path.read_bytes()
        if any(pattern.search(content) for pattern in _SECRET_PATTERNS):
            findings.append(Finding("secret", relative, "high-confidence secret material detected"))
        if any(pattern.search(content) for pattern in _ABSOLUTE_PATHS):
            findings.append(
                Finding("absolute_path", relative, "workstation-specific absolute path detected")
            )
        if path.name.endswith("Dockerfile"):
            for line in content.decode("utf-8", errors="ignore").splitlines():
                if line.startswith("FROM ") and "@sha256:" not in line:
                    findings.append(
                        Finding("mutable_base", relative, "container base is not digest pinned")
                    )
    ordered = tuple(sorted(findings, key=lambda item: (item.path, item.code)))
    return SecurityReport(not ordered, len(files), ordered)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    report = scan_root(args.root)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
