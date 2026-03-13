#!/usr/bin/env python3
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_review_v1.metrics import evaluate_participant
from contract_review_v1.reporting import dump_json_detail, participant_to_dict, render_markdown_report
from contract_review_v1.runner import generate_system_review, load_agent_module
from contract_review_v1.schema import ParsedReview, load_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate contract review quality for v1")
    parser.add_argument(
        "--dataset",
        default=str(CURRENT_DIR.parent / "data" / "sample_eval_dataset.json"),
        help="Path to evaluation dataset JSON",
    )
    parser.add_argument(
        "--output-dir",
        default=str(CURRENT_DIR.parent / "outputs"),
        help="Directory for markdown and json outputs",
    )
    parser.add_argument(
        "--agent-module",
        default=str(
            CURRENT_DIR.parent.parent.parent
            / "examples"
            / "Docs-by-LangChain"
            / "contract_review_agent.py"
        ),
        help="Path to existing contract_review_agent.py module",
    )
    parser.add_argument(
        "--skip-system",
        action="store_true",
        help="Skip local LLM generation and evaluate only imported baselines",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_dataset(dataset_path)

    third_party_predictions = [record.third_party for record in records]
    final_applied_predictions = [record.final_applied for record in records]

    system_predictions: list[ParsedReview]
    if args.skip_system:
        system_predictions = [
            ParsedReview(
                has_risk=False,
                risk_level=None,
                risk_points=[],
                explanation="",
                suggestion="",
                raw_text="(未执行本地模型，使用空结果占位)",
            )
            for _ in records
        ]
    else:
        agent_module_path = Path(args.agent_module).expanduser().resolve()
        agent_module = load_agent_module(agent_module_path)
        runtime_config = agent_module.configure_runtime_env()

        system_predictions = []
        for index, record in enumerate(records, start=1):
            print(f"[{index}/{len(records)}] Generating review for {record.contract_id}/{record.clause_id}")
            prediction = generate_system_review(
                record.clause_text,
                agent_module=agent_module,
                runtime_config=runtime_config,
            )
            system_predictions.append(prediction)

    participants = [
        evaluate_participant("第三方平台", records, third_party_predictions),
        evaluate_participant("最终应用版", records, final_applied_predictions),
        evaluate_participant("本系统 v1", records, system_predictions),
    ]

    markdown_report = render_markdown_report(participants)
    markdown_path = output_dir / "evaluation_report.md"
    markdown_path.write_text(markdown_report, encoding="utf-8")

    detail_payload = {
        "dataset": str(dataset_path),
        "participants": [participant_to_dict(item) for item in participants],
        "records": [
            {
                "contract_id": record.contract_id,
                "clause_id": record.clause_id,
                "clause_text": record.clause_text,
                "ground_truth": record.ground_truth.raw_text,
                "third_party": record.third_party.raw_text,
                "final_applied": record.final_applied.raw_text,
                "system": prediction.raw_text,
            }
            for record, prediction in zip(records, system_predictions)
        ],
    }
    json_path = output_dir / "evaluation_detail.json"
    dump_json_detail(json_path, detail_payload)

    print(f"Markdown report: {markdown_path}")
    print(f"JSON detail: {json_path}")


if __name__ == "__main__":
    main()
