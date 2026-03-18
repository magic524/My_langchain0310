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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--md-run-id", default="", help="Run id under datatype_test/outputs_md")
    group.add_argument("--md-run-dir", default="", help="Absolute path to any outputs_md run directory")
    parser.add_argument(
        "--output",
        default="",
        help="Output dataset JSON path. Default: Contract_Review_System/metrics/outputs/datasets/dataset_<run_id>.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.md_run_dir:
        run_id = Path(args.md_run_dir).name
        run_root_override: Path | None = Path(args.md_run_dir).expanduser().resolve()
    else:
        run_id = args.md_run_id
        run_root_override = None

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = (
            METRICS_ROOT / "outputs" / "datasets" / f"dataset_{run_id}.json"
        ).resolve()

    payload = build_dataset_from_md_run(
        project_root=PROJECT_ROOT,
        md_run_id=run_id,
        output_path=output_path,
        run_root=run_root_override,
    )

    print(f"Dataset generated: {output_path}")
    print(f"Contracts: {len(payload.contracts)}")
    print(f"Warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
