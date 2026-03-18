from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
METRICS_V2_ROOT = CURRENT_FILE.parents[1]
SRC_ROOT = METRICS_V2_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.parallel_review_report import (  # noqa: E402
    load_parallel_audits,
    write_contract_parallel_report,
    write_overall_summary_report,
)


def _file_safe_contract_id(contract_id: str) -> str:
    return contract_id.replace("/", "_").replace("\\", "_").replace(":", "：")


def main() -> None:
    """Generate per-contract and overall comparison reports."""

    parser = argparse.ArgumentParser(description="Generate three-way comparison reports")
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        required=True,
        help="Evaluation output directories, each containing dataset_with_local_llm.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for generated Markdown reports",
    )
    parser.add_argument(
        "--prefix",
        default="20260317_word2md_eval",
        help="Filename prefix for generated reports",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    audits = load_parallel_audits([Path(item).resolve() for item in args.run_dirs])
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_paths: list[Path] = []
    for audit in audits:
        path = output_dir / f"{args.prefix}_{_file_safe_contract_id(audit.contract_id)}_三方对照.md"
        generated_paths.append(write_contract_parallel_report(path, audit))

    overall_path = output_dir / f"{args.prefix}_总体汇总.md"
    generated_paths.append(write_overall_summary_report(overall_path, audits))

    for path in generated_paths:
        print(path)


if __name__ == "__main__":
    main()
