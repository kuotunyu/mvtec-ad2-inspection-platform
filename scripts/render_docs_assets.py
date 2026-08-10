# ruff: noqa: E501
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET_NAMES = (
    "architecture.svg",
    "workflow.svg",
    "screenshots/dashboard.webp",
    "screenshots/new-inspection.webp",
    "screenshots/job-evidence.webp",
    "screenshots/review.webp",
    "screenshots/model-evidence.webp",
)


def _architecture_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520" viewBox="0 0 1200 520" role="img" aria-labelledby="title desc"><title id="title">Inspection platform architecture</title><desc id="desc">A React workstation calls a FastAPI service backed by SQLite and an artifact store. A leased worker verifies a model registry and produces evidence.</desc><rect width="1200" height="520" fill="#071218"/><g font-family="Arial,sans-serif" fill="#dce8ec"><text x="60" y="70" font-size="30" font-weight="700">MVTec AD 2 inspection architecture</text><text x="60" y="104" font-size="16" fill="#87a2ad">Local-first · evidence-led · fail-closed</text></g><g stroke="#35d3e1" stroke-width="3" fill="#13242c"><rect x="60" y="170" width="210" height="150" rx="16"/><rect x="365" y="170" width="210" height="150" rx="16"/><rect x="670" y="170" width="210" height="150" rx="16"/><rect x="975" y="170" width="165" height="150" rx="16"/></g><g font-family="Arial,sans-serif" text-anchor="middle" fill="#e9f5f7"><text x="165" y="222" font-size="22" font-weight="700">React workstation</text><text x="165" y="258" font-size="15">submit · inspect · review</text><text x="470" y="222" font-size="22" font-weight="700">FastAPI</text><text x="470" y="258" font-size="15">validate · persist · report</text><text x="775" y="222" font-size="22" font-weight="700">Leased worker</text><text x="775" y="258" font-size="15">verify · infer · resume</text><text x="1057" y="222" font-size="22" font-weight="700">Registry</text><text x="1057" y="258" font-size="15">hash-locked bundles</text></g><g stroke="#f0ad2f" stroke-width="4" fill="none" marker-end="url(#arrow)"><path d="M270 245h80"/><path d="M575 245h80"/><path d="M880 245h80"/></g><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0 0L9 3L0 6Z" fill="#f0ad2f"/></marker></defs><g fill="#13242c" stroke="#49636e" stroke-width="2"><rect x="365" y="380" width="210" height="80" rx="14"/><rect x="670" y="380" width="210" height="80" rx="14"/></g><g font-family="Arial,sans-serif" text-anchor="middle" fill="#dce8ec"><text x="470" y="414" font-size="18" font-weight="700">SQLite WAL</text><text x="470" y="440" font-size="14">jobs · reviews · audit</text><text x="775" y="414" font-size="18" font-weight="700">Artifact store</text><text x="775" y="440" font-size="14">content-addressed · external</text></g><path d="M470 320v60M775 320v60" stroke="#49636e" stroke-width="3"/></svg>"""


def _workflow_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="360" viewBox="0 0 1200 360" role="img" aria-labelledby="title desc"><title id="title">Inspection evidence workflow</title><desc id="desc">A batch moves through validation, verified inference, pass or review routing, human disposition, and hashed reports.</desc><rect width="1200" height="360" fill="#071218"/><text x="60" y="64" font-family="Arial,sans-serif" font-size="30" font-weight="700" fill="#e9f5f7">Batch-to-review evidence workflow</text><g font-family="Arial,sans-serif" text-anchor="middle"><g fill="#13242c" stroke="#35d3e1" stroke-width="3"><rect x="45" y="135" width="175" height="100" rx="15"/><rect x="280" y="135" width="175" height="100" rx="15"/><rect x="515" y="135" width="175" height="100" rx="15"/><rect x="750" y="135" width="175" height="100" rx="15"/><rect x="985" y="135" width="175" height="100" rx="15"/></g><g fill="#e9f5f7" font-size="18" font-weight="700"><text x="132" y="181">Upload batch</text><text x="367" y="181">Decode + hash</text><text x="602" y="181">Verified inference</text><text x="837" y="181">PASS / REVIEW</text><text x="1072" y="181">Human + report</text></g><g fill="#87a2ad" font-size="13"><text x="132" y="207">local storage</text><text x="367" y="207">partial success</text><text x="602" y="207">leased worker</text><text x="837" y="207">model evidence</text><text x="1072" y="207">audited revision</text></g></g><g stroke="#f0ad2f" stroke-width="4"><path d="M220 185h60M455 185h60M690 185h60M925 185h60"/></g><text x="600" y="300" text-anchor="middle" font-family="Arial,sans-serif" font-size="17" fill="#f0ad2f">No automatic final rejection · no defect-type claim</text></svg>"""


def _write_svg_assets(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "architecture.svg").write_text(
        _architecture_svg() + "\n", encoding="utf-8", newline="\n"
    )
    (target / "workflow.svg").write_text(_workflow_svg() + "\n", encoding="utf-8", newline="\n")


def _write_generated(target: Path) -> None:
    _write_svg_assets(target)
    with TemporaryDirectory(prefix="mvtec-doc-capture-") as temporary:
        capture = Path(temporary)
        environment = dict(os.environ)
        environment["DOCS_SCREENSHOT_DIR"] = str(capture)
        subprocess.run(
            [
                "npx.cmd" if os.name == "nt" else "npx",
                "playwright",
                "test",
                "e2e/docs-assets.spec.ts",
                "--config=playwright.config.ts",
            ],
            cwd=ROOT / "apps/web",
            env=environment,
            check=True,
        )
        screenshot_root = target / "screenshots"
        screenshot_root.mkdir(parents=True, exist_ok=True)
        for source in sorted(capture.glob("*.png")):
            with Image.open(source) as image:
                image.save(
                    screenshot_root / f"{source.stem}.webp",
                    format="WEBP",
                    quality=86,
                    method=6,
                )
    manifest = {
        "assets": {
            name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in ASSET_NAMES
        },
        "fixture_scope": "synthetic-ci-only",
        "generator": "scripts/render_docs_assets.py",
        "schema_version": "1.0.0",
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _manifest_stale(destination: Path) -> tuple[str, ...]:
    manifest_path = destination / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        hashes = manifest["assets"]
        if (
            manifest["schema_version"] != "1.0.0"
            or manifest["fixture_scope"] != "synthetic-ci-only"
            or manifest["generator"] != "scripts/render_docs_assets.py"
            or set(hashes) != set(ASSET_NAMES)
        ):
            return ("manifest.json",)
    except (AttributeError, KeyError, OSError, TypeError, json.JSONDecodeError):
        return ("manifest.json",)
    return tuple(
        name
        for name in ASSET_NAMES
        if not (destination / name).is_file()
        or hashlib.sha256((destination / name).read_bytes()).hexdigest() != hashes[name]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--check-manifest", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "docs/assets"
    if args.check_manifest:
        stale_manifest = _manifest_stale(destination)
        if stale_manifest:
            print("stale documentation asset manifest: " + ", ".join(stale_manifest))
            return 1
        print("documentation asset manifest is current")
        return 0
    if not args.check:
        _write_generated(destination)
        print("rendered deterministic synthetic documentation assets")
        return 0
    with TemporaryDirectory(prefix="mvtec-doc-check-") as temporary:
        candidate = Path(temporary)
        _write_generated(candidate)
        stale_assets = [
            name
            for name in (*ASSET_NAMES, "manifest.json")
            if not (destination / name).is_file()
            or (destination / name).read_bytes() != (candidate / name).read_bytes()
        ]
    if stale_assets:
        print("stale documentation assets: " + ", ".join(stale_assets))
        return 1
    print("documentation assets are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
