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
SRC_DIR = METRICS_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_metrics.config import load_eval_config
from contract_metrics.evaluator import evaluate_dataset


def _parse_participants(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate contract review participants")
    parser.add_argument("--dataset", required=True, help="Built dataset JSON path")
    parser.add_argument("--agent-json", default="", help="Agent prediction JSON path")
    parser.add_argument("--agent-md", default="", help="Agent prediction markdown path")
    parser.add_argument(
        "--config",
        default=str(METRICS_ROOT / "config" / "defaults.json"),
        help="Evaluation config JSON path",
    )
    parser.add_argument(
        "--participants",
        default="",
        help="Comma-separated participants, e.g. third_party,final_applied,agent",
    )
    parser.add_argument("--use-llm-judge", action="store_true", help="Enable LLM judge")
    parser.add_argument(
        "--output",
        default="",
        help="Output evaluation payload JSON path. Default: metrics/outputs/eval_runs/<timestamp>/evaluation_payload.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    dataset_path = Path(args.dataset).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()

    eval_config = load_eval_config(config_path)
    if args.participants:
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

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = (METRICS_ROOT / "outputs" / "eval_runs" / run_id / "evaluation_payload.json").resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
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

    print(f"Evaluation payload: {output_path}")
    print(f"Participant-policy results: {len(payload.participant_results)}")
    print(f"Warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
