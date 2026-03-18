from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
SRC_ROOT = CURRENT_FILE.parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.dataset_builder import build_dataset


def main() -> None:
    """构建 metrics_v2 数据集。"""

    parser = argparse.ArgumentParser(description="Build metrics_v2 dataset from word2md outputs")
    parser.add_argument("--run-id", required=True, help="word2md run id")
    parser.add_argument(
        "--output",
        default="",
        help="Optional dataset output path. Default: Contract_Review_System/metrics_v2/outputs/datasets/dataset_<run_id>.json",
    )
    args = parser.parse_args()

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = (
            PROJECT_ROOT
            / "Contract_Review_System"
            / "metrics_v2"
            / "outputs"
            / "datasets"
            / f"dataset_{args.run_id}.json"
        ).resolve()

    payload = build_dataset(PROJECT_ROOT, args.run_id, output_path)
    print(f"dataset built: {output_path}")
    print(f"contracts: {len(payload.contracts)}")
    print(f"warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
