#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
METRICS_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = METRICS_ROOT.parent.parent
SRC_DIR = METRICS_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_metrics.config import load_eval_config
from contract_metrics.dataset_builder import build_dataset_from_md_run
from contract_metrics.evaluator import evaluate_dataset, load_dataset
from contract_metrics.prompt_runner import run_prompt_only_review
from contract_metrics.reporter import write_reports
from contract_metrics.types import EvaluationPayload


def _parse_participants(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-command prompt-only benchmark: build dataset -> run model -> evaluate -> report"
    )
    parser.add_argument("--md-run-id", required=True, help="Run id under datatype_test/outputs_md")
    parser.add_argument(
        "--participants",
        default="third_party,final_applied,agent",
        help="Comma-separated participants. Default: third_party,final_applied,agent",
    )
    parser.add_argument(
        "--config",
        default=str(METRICS_ROOT / "config" / "defaults.json"),
        help="Evaluation config JSON path",
    )
    parser.add_argument("--use-llm-judge", action="store_true", help="Enable LLM judge for scoring")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Default: metrics/outputs/eval_runs/<timestamp>_one_shot",
    )
    return parser.parse_args()


def _resolve_output_dir(raw_output: str) -> Path:
    if raw_output:
        return Path(raw_output).expanduser().resolve()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (METRICS_ROOT / "outputs" / "eval_runs" / f"{run_id}_one_shot").resolve()


def _safe_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _collect_fn_examples(payload: EvaluationPayload, participant: str, policy: str, limit: int = 10) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for contract in payload.contract_results:
        contract_id = str(contract.get("contract_id", ""))
        for row in contract.get("participant_results", []):
            if row.get("participant") != participant or row.get("policy") != policy:
                continue
            detail = row.get("detail", {})
            for clause in detail.get("clause_details", []):
                label_positive = bool(clause.get("label_positive", False))
                predicted_positive = bool(clause.get("predicted_positive", False))
                if label_positive and not predicted_positive:
                    text = str(clause.get("clause_text", "")).replace("\n", " ").strip()
                    examples.append(
                        {
                            "contract_id": contract_id,
                            "clause_id": str(clause.get("clause_id", "")),
                            "clause_text": text[:180],
                        }
                    )
                    if len(examples) >= limit:
                        return examples
    return examples


def _write_run_trace(
    *,
    output_dir: Path,
    args: argparse.Namespace,
    dataset_path: Path,
    participants: list[str],
    payload: EvaluationPayload,
    outputs: dict[str, str],
    agent_md_path: Path | None,
    agent_risk_count: int,
    agent_runtime: dict[str, Any] | None,
) -> Path:
    trace_path = output_dir / "RUN_TRACE.md"

    lines = [
        "# Prompt Eval Run Trace",
        "",
        "## Inputs",
        "",
        f"- md_run_id: `{args.md_run_id}`",
        f"- dataset: `{dataset_path}`",
        f"- participants: {', '.join(participants)}",
        f"- config: `{Path(args.config).expanduser().resolve()}`",
        f"- use_llm_judge: `{args.use_llm_judge}`",
        "",
        "## Agent Runtime",
        "",
    ]

    if agent_md_path is None:
        lines.append("- agent generation: skipped (participant `agent` not selected)")
    else:
        lines.append(f"- agent markdown: `{agent_md_path}`")
        lines.append(f"- agent detected risk clauses: `{agent_risk_count}`")
        if agent_runtime:
            lines.append(f"- model_name: `{agent_runtime.get('model_name', '')}`")
            lines.append(f"- base_url: `{agent_runtime.get('base_url', '')}`")
            lines.append(f"- temperature: `{agent_runtime.get('temperature', '')}`")
            lines.append(f"- api_key_masked: `{agent_runtime.get('api_key_masked', '')}`")
            lines.append(f"- extra_body: `{json.dumps(agent_runtime.get('extra_body', {}), ensure_ascii=False)}`")

    lines.extend([
        "",
        "## Summary Metrics",
        "",
        "| Participant | Policy | Accuracy | Miss Rate | False Positive Rate | TP | FP | TN | FN |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])

    for item in payload.participant_results:
        counts = item.identification.counts
        lines.append(
            f"| {item.participant} | {item.policy} | {_safe_pct(item.identification.accuracy)} | "
            f"{_safe_pct(item.identification.miss_rate)} | {_safe_pct(item.identification.false_positive_rate)} | "
            f"{counts.tp} | {counts.fp} | {counts.tn} | {counts.fn} |"
        )

    lines.extend(["", "## Warnings", ""])
    if payload.warnings:
        for warning in payload.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    lines.extend(["", "## Artifacts", ""])
    for key, value in outputs.items():
        lines.append(f"- {key}: `{value}`")

    trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return trace_path


def _write_miss_analysis(output_dir: Path, payload: EvaluationPayload) -> Path:
    analysis_path = output_dir / "MISS_ANALYSIS.md"

    lines = [
        "# Miss Analysis",
        "",
        "This file lists high miss-rate participant/policy combinations and example FN clauses.",
        "",
    ]

    sorted_results = sorted(payload.participant_results, key=lambda x: x.identification.miss_rate, reverse=True)
    for item in sorted_results:
        miss_rate = item.identification.miss_rate
        counts = item.identification.counts
        lines.extend(
            [
                f"## {item.participant} / {item.policy}",
                "",
                f"- miss_rate: {_safe_pct(miss_rate)}",
                f"- counts: TP={counts.tp}, FP={counts.fp}, TN={counts.tn}, FN={counts.fn}",
            ]
        )
        examples = _collect_fn_examples(payload, participant=item.participant, policy=item.policy, limit=12)
        if not examples:
            lines.append("- fn_examples: none")
            lines.append("")
            continue

        lines.append("- fn_examples:")
        lines.append("")
        lines.append("| Contract | Clause ID | Clause Text (truncated) |")
        lines.append("|---|---|---|")
        for example in examples:
            text = example["clause_text"].replace("|", " ")
            lines.append(f"| {example['contract_id']} | {example['clause_id']} | {text} |")
        lines.append("")

    analysis_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return analysis_path


def main() -> None:
    args = parse_args()
    output_dir = _resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = (METRICS_ROOT / "outputs" / "datasets" / f"dataset_{args.md_run_id}.json").resolve()
    build_dataset_from_md_run(
        project_root=PROJECT_ROOT,
        md_run_id=args.md_run_id,
        output_path=dataset_path,
    )

    participants = _parse_participants(args.participants)

    agent_md_path: Path | None = None
    agent_risk_count = 0
    agent_runtime: dict[str, Any] | None = None
    if "agent" in participants:
        _, contracts, _ = load_dataset(dataset_path)
        agent_md_path = output_dir / "agent_review_report.md"
        agent_md_path, agent_risk_count, agent_runtime = run_prompt_only_review(
            contracts=contracts,
            output_markdown_path=agent_md_path,
        )
        print(f"Agent prompt-only output: {agent_md_path}")
        print(f"Agent detected risk clauses: {agent_risk_count}")

    eval_config = load_eval_config(Path(args.config).expanduser().resolve())
    eval_config.participants = participants
    if args.use_llm_judge:
        eval_config.use_llm_judge = True

    payload = evaluate_dataset(
        dataset_path=dataset_path,
        eval_config=eval_config,
        agent_json_path=None,
        agent_markdown_path=agent_md_path,
    )

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

    outputs = write_reports(output_dir, payload)
    run_trace_path = _write_run_trace(
        output_dir=output_dir,
        args=args,
        dataset_path=dataset_path,
        participants=participants,
        payload=payload,
        outputs=outputs,
        agent_md_path=agent_md_path,
        agent_risk_count=agent_risk_count,
        agent_runtime=agent_runtime,
    )
    miss_analysis_path = _write_miss_analysis(output_dir, payload)

    print(f"Dataset: {dataset_path}")
    print(f"Evaluation payload: {payload_path}")
    print(f"Participant-policy results: {len(payload.participant_results)}")
    print(f"Warnings: {len(payload.warnings)}")
    print("Report artifacts:")
    for key, value in outputs.items():
        print(f"- {key}: {value}")
    print(f"- run_trace: {run_trace_path}")
    print(f"- miss_analysis: {miss_analysis_path}")


if __name__ == "__main__":
    main()
