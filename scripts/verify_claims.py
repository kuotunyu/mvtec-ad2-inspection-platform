from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sized
from dataclasses import dataclass
from pathlib import Path

_CLAIM = re.compile(
    r"<!-- claim:(?P<display>[^|]+)\|(?P<source>[^|]+)\|(?P<pointer>[^|]+)\|(?P<format>[^ ]+) -->"
)


@dataclass(frozen=True)
class Claim:
    display: str
    source: Path
    pointer: str
    format_spec: str
    document: Path


@dataclass(frozen=True)
class ClaimReport:
    ok: bool
    checked: int
    errors: tuple[str, ...]


def extract_claims(documents: list[Path]) -> tuple[Claim, ...]:
    claims: list[Claim] = []
    for document in documents:
        for match in _CLAIM.finditer(document.read_text(encoding="utf-8")):
            claims.append(
                Claim(
                    display=match.group("display"),
                    source=Path(match.group("source")),
                    pointer=match.group("pointer"),
                    format_spec=match.group("format"),
                    document=document,
                )
            )
    return tuple(claims)


def _resolve(payload: object, pointer: str) -> object:
    current = payload
    for raw in pointer.strip("/").split("/") if pointer.strip("/") else ():
        part = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]  # type: ignore[index]
    return current


def verify_claims(claims: tuple[Claim, ...], root: Path) -> ClaimReport:
    errors: list[str] = []
    cache: dict[Path, object] = {}
    for claim in claims:
        source = (root / claim.source).resolve()
        try:
            payload = cache.setdefault(source, json.loads(source.read_text(encoding="utf-8")))
            value = _resolve(payload, claim.pointer)
            if claim.format_spec == "len":
                if not isinstance(value, Sized):
                    raise TypeError("claim target is not sized")
                rendered = str(len(value))
            else:
                rendered = format(value, claim.format_spec)
            if rendered != claim.display:
                errors.append(f"{claim.document}:{claim.display} != {rendered}")
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            errors.append(f"{claim.document}:{claim.source}:{type(exc).__name__}")
    errors.extend(verify_serving_evidence(root))
    return ClaimReport(not errors, len(claims), tuple(errors))


def verify_serving_evidence(root: Path) -> tuple[str, ...]:
    evidence = root / "docs/assets/evidence"
    serving = evidence / "serving-benchmark.json"
    if not serving.is_file():
        return ()
    try:
        from scripts.benchmark_serving import validate_serving_report

        payload = json.loads(serving.read_text(encoding="utf-8"))
        manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
        expected = manifest["files"]["serving-benchmark.json"]
        actual = hashlib.sha256(serving.read_bytes()).hexdigest()
        errors = list(validate_serving_report(payload))
        if expected != actual:
            errors.append("serving_evidence_hash")
        return tuple(sorted(set(errors)))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return ("serving_evidence_format",)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "documents",
        nargs="*",
        type=Path,
        default=[Path("README.md"), Path("docs/CASE_STUDY.md"), Path("docs/MODEL_CARD.md")],
    )
    args = parser.parse_args()
    report = verify_claims(extract_claims(args.documents), Path("."))
    print(
        json.dumps({"ok": report.ok, "checked": report.checked, "errors": report.errors}, indent=2)
    )
    return 0 if report.ok and report.checked else 1


if __name__ == "__main__":
    raise SystemExit(main())
