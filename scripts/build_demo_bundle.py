from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from inspection_platform.contracts.models import BundleFile, ModelBundleManifest

PREPROCESSING_SHA256 = hashlib.sha256(b"synthetic-demo-preprocess-v1").hexdigest()
THRESHOLD_CONTRACT = "synthetic-fixed-v1"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_demo_bundle(output: Path) -> tuple[ModelBundleManifest, ...]:
    """Create deterministic, synthetic-only model bundles for all categories."""
    champions = json.loads(Path("reports/champions.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    manifests: list[ModelBundleManifest] = []
    manifest_hashes: dict[str, str] = {}

    for category in sorted(champions["champions"]):
        payload_path = output / "categories" / category / "mock.json"
        _write_json(
            payload_path,
            {
                "category": category,
                "generator_version": "1.0.0",
                "runtime_kind": "mock",
                "seed": 42,
            },
        )
        relative_payload = payload_path.relative_to(output).as_posix()
        manifest = ModelBundleManifest(
            category=category,
            runtime_kind="mock",
            model_family=None,
            evaluation_scope="synthetic-ci-only",
            files=(
                BundleFile(
                    path=relative_payload,
                    sha256=_sha256(payload_path),
                    size=payload_path.stat().st_size,
                ),
            ),
            preprocessing_sha256=PREPROCESSING_SHA256,
            threshold=0.5,
        )
        manifest_path = output / "categories" / category / "manifest.json"
        _write_json(
            manifest_path,
            manifest.model_dump(mode="json", exclude_computed_fields=True),
        )
        manifests.append(manifest)
        manifest_hashes[category] = _sha256(manifest_path)

    _write_json(
        output / "contract-chain.json",
        {
            "bundle_manifest_sha256": manifest_hashes,
            "dataset_manifest_sha256": champions["dataset_manifest_sha256"],
            "metric_contract_version": "1.0.0",
            "preprocessing_sha256": PREPROCESSING_SHA256,
            "schema_version": "1.0.0",
            "threshold_contract": THRESHOLD_CONTRACT,
        },
    )
    return tuple(manifests)


def build_public_demo_fixtures(output: Path) -> None:
    """Generate visibly marked images without using any MVTec source pixels."""
    cases = (
        ("clean-control", "PASS", 1103, "clean"),
        ("scratch-review", "REVIEW", 2207, "scratch"),
        ("dent-review", "REVIEW", 3301, "dent"),
    )
    entries: list[dict[str, object]] = []
    for name, outcome, seed, defect in cases:
        image = Image.new("RGB", (320, 240), (25, 31, 36))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (55, 35, 265, 190), radius=20, fill=(151, 162, 168), outline=(211, 220, 224), width=4
        )
        draw.rectangle((0, 208, 320, 240), fill=(6, 18, 24))
        draw.text((88, 217), "SYNTHETIC DEMO", fill=(78, 225, 244))
        if defect == "scratch":
            draw.line((105, 70, 222, 160), fill=(39, 45, 49), width=6)
            draw.line((108, 68, 225, 158), fill=(232, 238, 240), width=2)
        elif defect == "dent":
            draw.ellipse((135, 85, 200, 150), fill=(92, 103, 110), outline=(223, 230, 233), width=3)
        image_path = output / "images" / f"{name}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(image_path, format="PNG", optimize=False)
        expected = {
            "evaluation_scope": "synthetic-ci-only",
            "generator_version": "1.0.0",
            "intended_mock_outcome": outcome,
            "seed": seed,
        }
        _write_json(output / "expected" / f"{name}.json", expected)
        entries.append(
            {
                "filename": f"images/{name}.png",
                "generator_version": "1.0.0",
                "intended_mock_outcome": outcome,
                "license": "CC0-1.0 project-generated",
                "seed": seed,
                "sha256": _sha256(image_path),
            }
        )
    _write_json(
        output / "manifest.json",
        {
            "evaluation_scope": "synthetic-ci-only",
            "fixtures": entries,
            "notice": "Generated geometry only; contains no MVTec pixels.",
            "schema_version": "1.0.0",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fixtures-root", type=Path)
    args = parser.parse_args()
    manifests = build_demo_bundle(args.output)
    if args.fixtures_root is not None:
        build_public_demo_fixtures(args.fixtures_root)
    print(f"built {len(manifests)} deterministic synthetic-only bundles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
