#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
METRICS_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = METRICS_ROOT.parent.parent
SRC_DIR = METRICS_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_metrics.config import load_eval_config
from contract_metrics.dataset_builder import build_dataset_from_md_run
from contract_metrics.evaluator import evaluate_dataset
from contract_metrics.reporter import write_reports


def _parse_participants(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate prompt-only agent performance (default: third_party vs agent)"
    )
    parser.add_argument("--md-run-id", default="", help="Run id under datatype_test/outputs_md")
    parser.add_argument("--dataset", default="", help="Built dataset JSON path")
    parser.add_argument("--agent-json", default="", help="Agent prediction JSON path")
    parser.add_argument("--agent-md", default="", help="Agent prediction markdown path")
    parser.add_argument(
        "--config",
        default=str(METRICS_ROOT / "config" / "defaults.json"),
        help="Evaluation config JSON path",
    )
    parser.add_argument(
        "--participants",
        default="third_party,agent",
        help="Comma-separated participants (default: third_party,agent)",
    )
    parser.add_argument("--use-llm-judge", action="store_true", help="Enable LLM judge")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Default: metrics/outputs/eval_runs/<timestamp>_prompt_only",
    )
    return parser.parse_args()


def _resolve_dataset_path(args: argparse.Namespace) -> Path:
    if args.dataset:
        return Path(args.dataset).expanduser().resolve()

    if not args.md_run_id:
        msg = "Either --dataset or --md-run-id is required"
        raise ValueError(msg)

    dataset_path = (
        METRICS_ROOT / "outputs" / "datasets" / f"dataset_{args.md_run_id}.json"
    ).resolve()
    build_dataset_from_md_run(
        project_root=PROJECT_ROOT,
        md_run_id=args.md_run_id,
        output_path=dataset_path,
    )
    return dataset_path


def _resolve_output_dir(raw_output: str) -> Path:
    if raw_output:
        return Path(raw_output).expanduser().resolve()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (METRICS_ROOT / "outputs" / "eval_runs" / f"{run_id}_prompt_only").resolve()


def main() -> None:
    args = parse_args()

    if not args.agent_json and not args.agent_md:
        msg = "At least one of --agent-json or --agent-md is required"
        raise ValueError(msg)

    dataset_path = _resolve_dataset_path(args)
    config_path = Path(args.config).expanduser().resolve()
    eval_config = load_eval_config(config_path)
    eval_config.participants = _parse_participants(args.participants)
    if args.use_llm_judge:
        eval_config.use_llm_judge = True

    agent_json_path = Path(args.agent_json).expanduser().resolve() if args.agent_json else None
    agent_md_path = Path(args.agent_md).expanduser().resolve() if args.agent_md else None

    payload = evaluate_dataset(
        dataset_path=dataset_path,
        eval_config=eval_config,
        agent_json_path=agent_json_path,
        agent_markdown_path=agent_md_path,
    )

    output_dir = _resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload_path = output_dir / "evaluation_payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "meta": payload.meta,
                "warnings": payload.warnings,
                "participant_results": [asdict(item) for item in payload.participant_results],
                "contract_results": payload.contract_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_outputs = write_reports(output_dir, payload)

    print(f"Dataset: {dataset_path}")
    print(f"Evaluation payload: {payload_path}")
    print(f"Participant-policy results: {len(payload.participant_results)}")
    print(f"Warnings: {len(payload.warnings)}")
    print("Report artifacts:")
    for key, value in report_outputs.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
