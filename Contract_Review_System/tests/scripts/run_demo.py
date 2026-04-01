from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
SRC_ROOT = CURRENT_FILE.parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_tests.dataset_builder import build_dataset
from contract_tests.evaluator import evaluate_dataset
from contract_tests.reporter import write_reports


def main() -> None:
    """一步构建数据集并评估。"""

    parser = argparse.ArgumentParser(description="Run tests demo pipeline")
    parser.add_argument("--run-id", required=True, help="word2md run id")
    args = parser.parse_args()

    dataset_path = (
        PROJECT_ROOT
        / "Contract_Review_System"
        / "tests"
        / "outputs"
        / "datasets"
        / f"dataset_{args.run_id}.json"
    ).resolve()
    build_dataset(PROJECT_ROOT, args.run_id, dataset_path)

    payload = evaluate_dataset(dataset_path, participants=["third_party"])
    output_dir = (
        PROJECT_ROOT
        / "Contract_Review_System"
        / "tests"
        / "outputs"
        / "eval_runs"
        / args.run_id
    ).resolve()
    files = write_reports(output_dir, payload)

    print(f"dataset: {dataset_path}")
    print(f"report: {files['markdown']}")


if __name__ == "__main__":
    main()
