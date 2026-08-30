from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from experiments.drift.artifacts import build_drift_report
from experiments.train import write_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build offline anomaly-score distribution drift evidence"
    )
    parser.add_argument("--baseline-artifact", required=True, nargs="+", type=Path)
    parser.add_argument("--current-artifact", required=True, nargs="+", type=Path)
    parser.add_argument("--baseline-description", required=True)
    parser.add_argument("--current-description", required=True)
    parser.add_argument("--bins", default=10, type=int)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_drift_report(
        baseline_artifacts=args.baseline_artifact,
        current_artifacts=args.current_artifact,
        baseline_description=args.baseline_description,
        current_description=args.current_description,
        bins=args.bins,
    )
    output = write_contract(args.output, report)
    print(
        json.dumps(
            {
                "categories": [item.category for item in report.comparisons],
                "output": str(output),
                "status": "written",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
