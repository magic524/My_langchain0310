from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .metrics import DimensionResult, MetricExample, ParticipantMetrics


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _render_example(title: str, example: MetricExample | None) -> list[str]:
    lines = [f"#### {title}", ""]
    if example is None:
        lines.append("无可用示例。")
        lines.append("")
        return lines

    lines.extend(
        [
            f"- 合同: {example.contract_id}",
            f"- 条款: {example.clause_id}",
            f"- 原文: {example.clause_text}",
            f"- 预测: {example.predicted_text}",
            f"- 参考: {example.reference_text}",
            f"- 说明: {example.reason}",
            "",
        ]
    )
    return lines


def _render_dimension(title: str, result: DimensionResult) -> list[str]:
    lines = [f"### {title}", "", f"- 平均分: {_fmt_pct(result.score)}", ""]
    lines.extend(_render_example("正确示例", result.correct_example))
    lines.extend(_render_example("错误示例", result.wrong_example))
    return lines


def render_markdown_report(participants: list[ParticipantMetrics]) -> str:
    """Render the evaluation markdown report.

    Args:
        participants: Metrics for all compared participants.

    Returns:
        Markdown report content.
    """

    lines = [
        "# 合同审查 v1 评测报告",
        "",
        "本报告对三类对象做对比：第三方平台、最终应用版、本系统 v1（prompt-only）。",
        "",
        "## 指标一：风险点识别",
        "",
        "| 对象 | 准确率 | 漏报率 | 误报率 |",
        "|---|---:|---:|---:|",
    ]

    for item in participants:
        lines.append(
            f"| {item.name} | {_fmt_pct(item.risk_accuracy)} | {_fmt_pct(item.risk_miss_rate)} | {_fmt_pct(item.risk_false_positive_rate)} |"
        )

    lines.append("")
    for item in participants:
        lines.append(f"## {item.name}")
        lines.append("")
        lines.extend(_render_dimension("指标二：风险解释准确率", item.explanation_accuracy))
        lines.extend(_render_dimension("指标三：修改建议准确率", item.suggestion_accuracy))

    return "\n".join(lines).strip() + "\n"


def dump_json_detail(output_path: Path, payload: dict[str, Any]) -> None:
    """Persist detailed JSON report."""

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def participant_to_dict(item: ParticipantMetrics) -> dict[str, Any]:
    """Convert dataclasses to JSON-ready dict."""

    return asdict(item)
