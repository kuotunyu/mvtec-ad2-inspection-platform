from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from jsonschema import Draft202012Validator

from experiments.evaluate_public import PublicBenchmark, load_public_benchmark
from experiments.select_champions import ChampionsArtifact


def load_champions(path: Path) -> ChampionsArtifact:
    payload = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("champions root must be an object")
    canonical = payload.pop("canonical_sha256", None)
    artifact = ChampionsArtifact.model_validate(payload)
    if canonical != artifact.identity:
        raise ValueError("champions canonical identity mismatch")
    return artifact


def validate_benchmark_schema(benchmark_path: Path, schema_path: Path) -> None:
    document = json.loads(benchmark_path.resolve(strict=True).read_text(encoding="utf-8"))
    schema = json.loads(schema_path.resolve(strict=True).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(document)


def render_markdown(benchmark: PublicBenchmark, champions: ChampionsArtifact) -> str:
    if (
        champions.public_benchmark_sha256 != benchmark.identity
        or champions.dataset_manifest_sha256 != benchmark.dataset_manifest_sha256
        or champions.public_gate_identity != benchmark.public_gate_identity
    ):
        raise ValueError("champions are not traceable to the supplied benchmark")
    lines = [
        "# MVTec AD 2 Public Benchmark",
        "",
        "This report is generated only from the canonical aggregate JSON artifacts.",
        "Raw images, anomaly maps, checkpoints, and private outputs are not included.",
        "",
        f"- Public benchmark SHA-256: `{benchmark.identity}`",
        f"- Champions SHA-256: `{champions.identity}`",
        f"- Dataset manifest SHA-256: `{benchmark.dataset_manifest_sha256}`",
        f"- Public gate SHA-256: `{benchmark.public_gate_identity}`",
        "- Common pixel evaluation size: "
        f"`{benchmark.evaluation_size[0]}x{benchmark.evaluation_size[1]}`",
        "",
        "## Frozen category champions",
        "",
        "| Category | Champion | Mean AU-PRO | Mean image AUROC | GPU p95 ms | "
        "Peak VRAM MiB | Artifact bytes | Selection reason | Run evidence |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for category_decision in champions.decisions:
        winner = next(
            candidate
            for candidate in category_decision.candidates
            if candidate.family == category_decision.decision.winner
        )
        evidence = "<br>".join(f"`{identity}`" for identity in winner.run_identities)
        lines.append(
            "| "
            f"{category_decision.category} | {winner.family} | {winner.au_pro:.6f} | "
            f"{winner.image_auroc:.6f} | {winner.gpu_p95_latency_ms:.3f} | "
            f"{winner.peak_vram_mib:.3f} | {winner.artifact_size_bytes} | "
            f"{category_decision.decision.reason} | {evidence} |"
        )

    lines.extend(
        [
            "",
            "## Seed-42 screening",
            "",
            "| Family | Macro AU-PRO (95% CI) | Macro image AUROC (95% CI) | Run evidence |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for summary in benchmark.screening_macro:
        evidence = "<br>".join(f"`{identity}`" for identity in summary.run_identities)
        lines.append(
            f"| {summary.family} | {summary.au_pro.mean:.6f} "
            f"[{summary.au_pro.lower:.6f}, {summary.au_pro.upper:.6f}] | "
            f"{summary.image_auroc.mean:.6f} "
            f"[{summary.image_auroc.lower:.6f}, {summary.image_auroc.upper:.6f}] | "
            f"{evidence} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Champion comparisons contain exactly three seeds (17, 42, and 2026). "
            "Their paired bootstrap intervals describe uncertainty within those repeats; "
            "they are not formal inferential guarantees, and no multiplicity correction "
            "was applied.",
            "- Public results selected contenders and category champions through iterative "
            "evaluation, so `test_public` is not an independent final holdout. Private "
            "results have not selected or tuned them.",
            "- The independent official private validation is `PRIVATE-NO-GO`; this report "
            "does not establish private generalization or production model quality.",
            "- GPU latency is batch-size-1 model execution on the recorded local CUDA "
            "environment; setup time is reported separately in JSON.",
            "- Peak VRAM is the maximum allocated during the frozen public prediction run.",
            "- CPU latency and official private/private-mixed metrics are not evaluated "
            "in this artifact.",
            "",
        ]
    )
    return "\n".join(lines)


def render_champion_svg(benchmark: PublicBenchmark, champions: ChampionsArtifact) -> str:
    width = 920
    height = 410
    bar_width = 82
    gap = 26
    x_start = 58
    chart_height = 270
    baseline = 320
    colors = {
        "patchcore": "#2563eb",
        "efficient_ad": "#059669",
        "dinomaly": "#d97706",
    }
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f"<desc>Generated from public benchmark {benchmark.identity} "
        f"and champions {champions.identity}</desc>",
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<text x="40" y="34" font-family="system-ui" font-size="20" '
        'font-weight="700" fill="#0f172a">Frozen champion mean AU-PRO by category</text>',
        f'<line x1="40" y1="{baseline}" x2="{width - 30}" y2="{baseline}" stroke="#94a3b8"/>',
    ]
    for index, decision in enumerate(champions.decisions):
        winner = next(
            candidate
            for candidate in decision.candidates
            if candidate.family == decision.decision.winner
        )
        x = x_start + index * (bar_width + gap)
        bar_height = winner.au_pro * chart_height
        y = baseline - bar_height
        elements.extend(
            [
                f'<rect x="{x}" y="{y:.2f}" width="{bar_width}" '
                f'height="{bar_height:.2f}" rx="4" fill="{colors[winner.family]}"/>',
                f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.2f}" '
                'text-anchor="middle" font-family="system-ui" font-size="12" '
                f'fill="#0f172a">{winner.au_pro:.3f}</text>',
                f'<text x="{x + bar_width / 2:.1f}" y="{baseline + 20}" '
                'text-anchor="middle" font-family="system-ui" font-size="11" '
                f'fill="#334155">{decision.category}</text>',
                f'<text x="{x + bar_width / 2:.1f}" y="{baseline + 37}" '
                'text-anchor="middle" font-family="system-ui" font-size="10" '
                f'fill="#64748b">{winner.family}</text>',
            ]
        )
    elements.append("</svg>\n")
    return "\n".join(elements)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render canonical public benchmark reports")
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--champions", type=Path)
    parser.add_argument("--contenders", type=Path)
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument(
        "--schema", type=Path, default=Path("reports/schemas/benchmark.schema.json")
    )
    parser.add_argument("--figure-root", type=Path, default=Path("docs/assets/bench"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runs_value = os.environ.get("MVTECAD2_RUNS_ROOT")
    evidence_root = Path(runs_value).expanduser().resolve() / "evidence" if runs_value else None
    benchmark_source = (
        args.benchmark.expanduser().resolve(strict=True)
        if args.benchmark is not None
        else evidence_root / "public_benchmark.json"
        if evidence_root is not None
        else Path("reports/public_benchmark.json").resolve(strict=True)
    )
    champions_source = (
        args.champions.expanduser().resolve(strict=True)
        if args.champions is not None
        else evidence_root / "champions.json"
        if evidence_root is not None
        else Path("reports/champions.json").resolve(strict=True)
    )
    contenders_source = (
        args.contenders.expanduser().resolve(strict=True)
        if args.contenders is not None
        else evidence_root / "contenders.json"
        if evidence_root is not None
        else Path("reports/contenders.json").resolve(strict=True)
    )
    schema_path = args.schema.expanduser().resolve(strict=True)
    validate_benchmark_schema(benchmark_source, schema_path)
    benchmark = load_public_benchmark(benchmark_source)
    champions = load_champions(champions_source)
    reports_root = args.reports_root.expanduser().resolve()
    reports_root.mkdir(parents=True, exist_ok=True)
    for source, name in (
        (benchmark_source, "public_benchmark.json"),
        (champions_source, "champions.json"),
        (contenders_source, "contenders.json"),
    ):
        destination = reports_root / name
        if source != destination:
            shutil.copyfile(source, destination)
    _write_text(reports_root / "benchmark.md", render_markdown(benchmark, champions))
    figure_root = args.figure_root.expanduser().resolve()
    _write_text(
        figure_root / "champion-au-pro.svg",
        render_champion_svg(benchmark, champions),
    )
    print(
        json.dumps(
            {
                "benchmark_sha256": benchmark.identity,
                "champions_sha256": champions.identity,
                "report": str(reports_root / "benchmark.md"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
