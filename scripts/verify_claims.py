from __future__ import annotations

import argparse
import hashlib
import json
import math
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
    errors.extend(verify_official_private_evidence(root))
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


def verify_official_private_evidence(root: Path) -> tuple[str, ...]:
    evidence = root / "docs/assets/evidence"
    official = evidence / "official-private-result.json"
    if not official.is_file():
        return ()
    try:
        payload = json.loads(official.read_text(encoding="utf-8"))
        manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
        errors: list[str] = []
        expected_hash = manifest["files"]["official-private-result.json"]
        if hashlib.sha256(official.read_bytes()).hexdigest() != expected_hash:
            errors.append("official_private_evidence_hash")
        if (
            payload.get("schema_version") != "1.0.0"
            or payload.get("benchmark") != "MVTec AD 2"
            or payload.get("status") != "DONE"
            or payload.get("verdict") != "PRIVATE-NO-GO"
            or payload.get("thresholded_metrics_available") is not False
            or payload.get("archive_inventory") != {"anomaly_map_tiff": 4090, "thresholded_png": 0}
            or not re.fullmatch(r"[0-9a-f]{64}", payload.get("submission_archive_sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", payload.get("submission_id_sha256", ""))
        ):
            errors.append("official_private_evidence_schema")
        categories = {
            "can",
            "fabric",
            "fruit_jelly",
            "rice",
            "sheet_metal",
            "vial",
            "wallplugs",
            "walnuts",
        }
        metrics = payload["metrics"]
        if set(metrics) != {"private", "private_mixed"}:
            errors.append("official_private_evidence_metrics")
        for split in ("private", "private_mixed"):
            split_metrics = metrics[split]
            if set(split_metrics) != {"auc_pro_0_05", "class_f1", "seg_f1"}:
                errors.append("official_private_evidence_metrics")
                continue
            for metric_name, metric in split_metrics.items():
                values = metric["categories"]
                if set(values) != categories or any(
                    not isinstance(value, int | float)
                    or not math.isfinite(value)
                    or not 0 <= value <= 100
                    for value in values.values()
                ):
                    errors.append("official_private_evidence_metrics")
                    continue
                expected_average = round(sum(values.values()) / len(values), 2)
                if not math.isclose(metric["average"], expected_average, abs_tol=0.01):
                    errors.append("official_private_evidence_metrics")
                if metric_name in {"class_f1", "seg_f1"} and any(values.values()):
                    errors.append("official_private_evidence_metrics")
        return tuple(sorted(set(errors)))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return ("official_private_evidence_format",)


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
