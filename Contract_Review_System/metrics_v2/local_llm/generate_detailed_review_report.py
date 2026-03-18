from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
METRICS_V2_ROOT = CURRENT_FILE.parents[1]
SRC_ROOT = METRICS_V2_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.local_llm_review_report import (  # noqa: E402
    load_contract_audits,
    write_local_llm_review_report,
)


def main() -> None:
    """Generate a reviewer-friendly Markdown report for local LLM outputs."""

    parser = argparse.ArgumentParser(description="Generate a detailed local_llm review report")
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        required=True,
        help="One or more evaluation output directories, each containing dataset_with_local_llm.json",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Markdown file to write",
    )
    args = parser.parse_args()

    audits = load_contract_audits([Path(item).resolve() for item in args.run_dirs])
    output_path = write_local_llm_review_report(Path(args.output_file).resolve(), audits)
    print(output_path)


if __name__ == "__main__":
    main()
