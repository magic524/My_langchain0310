from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .io_utils import write_text
from .types import EvaluationPayload, ParticipantPolicyResult


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _policy_title(policy: str) -> str:
    if policy == "policy_a":
        return "口径A（采纳+部分采纳为正例）"
    if policy == "policy_b":
        return "口径B（全部意见为正例）"
    return policy


def _group_by_policy(results: list[ParticipantPolicyResult]) -> dict[str, list[ParticipantPolicyResult]]:
    grouped: dict[str, list[ParticipantPolicyResult]] = {}
    for item in results:
        grouped.setdefault(item.policy, []).append(item)
    return grouped


def render_markdown_report(payload: EvaluationPayload) -> str:
    """Render markdown evaluation report.

    Args:
        payload: Evaluation payload.

    Returns:
        Markdown report content.
    """
    grouped = _group_by_policy(payload.participant_results)

    lines = [
        "# Contract Metrics Evaluation Report",
        "",
        "## 概览",
        "",
        f"- 数据集: `{payload.meta.get('dataset_path', '')}`",
        f"- 参与方: {', '.join(payload.meta.get('participants', []))}",
        f"- LLM 裁判: {'开启' if payload.meta.get('use_llm_judge') else '关闭'}",
        f"- 警告数: {len(payload.warnings)}",
        "",
    ]

    for policy in sorted(grouped.keys()):
        lines.extend(
            [
                f"## {_policy_title(policy)}",
                "",
                "| Participant | Risk Accuracy | Miss Rate | False Positive Rate | Explanation Direction | Explanation Accuracy | Explanation Completeness | Suggestion Direction | Suggestion Accuracy | Suggestion Completeness |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in sorted(grouped[policy], key=lambda value: value.participant):
            lines.append(
                "| {participant} | {risk_acc} | {miss} | {fpr} | {exp_dir} | {exp_acc} | {exp_comp} | {sug_dir} | {sug_acc} | {sug_comp} |".format(
                    participant=item.participant,
                    risk_acc=_fmt_pct(item.identification.accuracy),
                    miss=_fmt_pct(item.identification.miss_rate),
                    fpr=_fmt_pct(item.identification.false_positive_rate),
                    exp_dir=_fmt_pct(item.explanation.direction_consistency),
                    exp_acc=_fmt_pct(item.explanation.accuracy),
                    exp_comp=_fmt_pct(item.explanation.completeness),
                    sug_dir=_fmt_pct(item.suggestion.direction_consistency),
                    sug_acc=_fmt_pct(item.suggestion.content_accuracy),
                    sug_comp=_fmt_pct(item.suggestion.completeness),
                )
            )
        lines.append("")

    lines.extend(["## 分合同概览", ""])
    for contract in payload.contract_results:
        contract_id = contract.get("contract_id", "")
        lines.append(f"### {contract_id}")
        lines.append("")

        participant_rows = contract.get("participant_results", [])
        lines.append("| Participant | Policy | TP | FP | TN | FN |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for row in participant_rows:
            metrics = row.get("metrics", {})
            identification = metrics.get("identification", {})
            counts = identification.get("counts", {})
            lines.append(
                f"| {row.get('participant', '')} | {row.get('policy', '')} | {counts.get('tp', 0)} | {counts.get('fp', 0)} | {counts.get('tn', 0)} | {counts.get('fn', 0)} |"
            )
        lines.append("")

    lines.extend(["## 解析告警", ""])
    if payload.warnings:
        for warning in payload.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- 无")
    lines.append("")

    return "\n".join(lines)


def write_csv_report(path: Path, results: list[ParticipantPolicyResult]) -> None:
    """Write participant policy metrics to CSV.

    Args:
        path: Output csv path.
        results: Participant policy results.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "participant",
                "policy",
                "risk_accuracy",
                "miss_rate",
                "false_positive_rate",
                "explanation_direction_consistency",
                "explanation_accuracy",
                "explanation_completeness",
                "suggestion_direction_consistency",
                "suggestion_content_accuracy",
                "suggestion_completeness",
            ]
        )

        for item in results:
            writer.writerow(
                [
                    item.participant,
                    item.policy,
                    item.identification.accuracy,
                    item.identification.miss_rate,
                    item.identification.false_positive_rate,
                    item.explanation.direction_consistency,
                    item.explanation.accuracy,
                    item.explanation.completeness,
                    item.suggestion.direction_consistency,
                    item.suggestion.content_accuracy,
                    item.suggestion.completeness,
                ]
            )


def write_reports(output_dir: Path, payload: EvaluationPayload) -> dict[str, str]:
    """Write markdown/json/csv evaluation outputs.

    Args:
        output_dir: Output directory.
        payload: Evaluation payload.

    Returns:
        Output file map.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "evaluation_result.json"
    md_path = output_dir / "evaluation_report.md"
    csv_path = output_dir / "evaluation_metrics.csv"
    summary_path = output_dir / "README_summary.md"

    json_path.write_text(
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

    markdown = render_markdown_report(payload)
    write_text(md_path, markdown)

    write_csv_report(csv_path, payload.participant_results)

    summary_lines = [
        "# Metrics Run Summary",
        "",
        f"- dataset_path: `{payload.meta.get('dataset_path', '')}`",
        f"- participants: {', '.join(payload.meta.get('participants', []))}",
        f"- use_llm_judge: {payload.meta.get('use_llm_judge')}",
        f"- warnings: {len(payload.warnings)}",
        "",
        "Artifacts:",
        f"- `{json_path.name}`",
        f"- `{md_path.name}`",
        f"- `{csv_path.name}`",
    ]
    write_text(summary_path, "\n".join(summary_lines) + "\n")

    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "csv": str(csv_path),
        "summary": str(summary_path),
    }
