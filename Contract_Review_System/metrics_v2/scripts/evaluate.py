from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
SRC_ROOT = CURRENT_FILE.parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.evaluator import evaluate_dataset
from contract_metrics_v2.reporter import write_reports


def main() -> None:
    """运行 metrics_v2 评估。"""

    parser = argparse.ArgumentParser(description="Evaluate baselines with metrics_v2")
    parser.add_argument("--run-id", required=True, help="word2md run id")
    parser.add_argument(
        "--dataset",
        default="",
        help="Optional dataset path. Default: Contract_Review_System/metrics_v2/outputs/datasets/dataset_<run_id>.json",
    )
    parser.add_argument(
        "--participants",
        default="third_party,final_applied",
        help="Comma-separated participants",
    )
    parser.add_argument("--clause-threshold", type=float, default=0.33, help="Clause alignment threshold")
    parser.add_argument("--risk-threshold", type=float, default=0.45, help="Risk pair threshold")
    args = parser.parse_args()

    if args.dataset:
        dataset_path = Path(args.dataset).resolve()
    else:
        dataset_path = (
            PROJECT_ROOT
            / "Contract_Review_System"
            / "metrics_v2"
            / "outputs"
            / "datasets"
            / f"dataset_{args.run_id}.json"
        ).resolve()

    participants = [item.strip() for item in args.participants.split(",") if item.strip()]
    payload = evaluate_dataset(
        dataset_path,
        participants=participants,
        clause_match_threshold=args.clause_threshold,
        risk_match_threshold=args.risk_threshold,
    )
    output_dir = (
        PROJECT_ROOT
        / "Contract_Review_System"
        / "metrics_v2"
        / "outputs"
        / "eval_runs"
        / args.run_id
    ).resolve()
    files = write_reports(output_dir, payload)
    print(f"evaluation json: {files['json']}")
    print(f"evaluation report: {files['markdown']}")
    print(f"warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
