from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
SRC_ROOT = CURRENT_FILE.parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_tests.evaluator import evaluate_dataset
from contract_tests.local_llm_review_pipeline import (
    generate_parallel_comparison_outputs,
    has_local_llm_participant,
    prepare_dataset_for_evaluation,
)
from contract_tests.reporter import write_reports


def main() -> None:
    """运行 tests 评估。"""

    parser = argparse.ArgumentParser(description="Evaluate baselines with tests")
    parser.add_argument("--run-id", required=True, help="word2md run id")
    parser.add_argument(
        "--dataset",
        default="",
        help="可选，显式指定数据集路径。默认读取 Contract_Review_System/tests/outputs/datasets/。",
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
            / "tests"
            / "outputs"
            / "datasets"
            / f"dataset_{args.run_id}.json"
        ).resolve()

    output_dir = (
        PROJECT_ROOT
        / "Contract_Review_System"
        / "tests"
        / "outputs"
        / "eval_runs"
        / args.run_id
    ).resolve()
    prepared_dataset_path = prepare_dataset_for_evaluation(dataset_path, output_dir)

    participants = [item.strip() for item in args.participants.split(",") if item.strip()]
    dataset_has_local_llm = has_local_llm_participant(prepared_dataset_path)
    if dataset_has_local_llm:
        for required_participant in ("third_party", "local_llm"):
            if required_participant not in participants:
                participants.append(required_participant)

    payload = evaluate_dataset(
        prepared_dataset_path,
        participants=participants,
        clause_match_threshold=args.clause_threshold,
        risk_match_threshold=args.risk_threshold,
    )
    files = write_reports(output_dir, payload)
    if dataset_has_local_llm:
        comparison_outputs = generate_parallel_comparison_outputs(
            prepared_dataset_path,
            output_dir,
            args.run_id,
            participants,
        )
        print(f"comparison dir: {comparison_outputs['compare_root']}")
    print(f"evaluation json: {files['json']}")
    print(f"evaluation report: {files['markdown']}")
    print(f"warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
