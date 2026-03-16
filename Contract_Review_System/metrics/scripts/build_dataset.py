#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
METRICS_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = METRICS_ROOT.parent.parent
SRC_DIR = METRICS_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_metrics.dataset_builder import build_dataset_from_md_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build metrics dataset from datatype_test markdown run")
    parser.add_argument("--md-run-id", required=True, help="Run id under datatype_test/outputs_md")
    parser.add_argument(
        "--output",
        default="",
        help="Output dataset JSON path. Default: Contract_Review_System/metrics/outputs/datasets/dataset_<run_id>.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = (
            METRICS_ROOT / "outputs" / "datasets" / f"dataset_{args.md_run_id}.json"
        ).resolve()

    payload = build_dataset_from_md_run(
        project_root=PROJECT_ROOT,
        md_run_id=args.md_run_id,
        output_path=output_path,
    )

    print(f"Dataset generated: {output_path}")
    print(f"Contracts: {len(payload.contracts)}")
    print(f"Warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
