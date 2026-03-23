from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .io_utils import write_text
from .types import EvaluationPayload, ParticipantPolicyMetrics


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _policy_name(policy: str) -> str:
    if policy == "adopted_only":
        return "口径A（采纳 + 部分采纳）"
    if policy == "all_labeled":
        return "口径B（采纳说明全部意见）"
    return policy


def _group_by_policy(results: list[ParticipantPolicyMetrics]) -> dict[str, list[ParticipantPolicyMetrics]]:
    grouped: dict[str, list[ParticipantPolicyMetrics]] = {}
    for item in results:
        grouped.setdefault(item.policy, []).append(item)
    return grouped


def render_markdown_report(payload: EvaluationPayload) -> str:
    """渲染 Markdown 报告。"""

    grouped = _group_by_policy(payload.participant_results)
    single_contract = payload.meta.get("single_contract") or {}
    lines = [
        "# Contract Metrics V2 Evaluation Report",
        "",
        "## 概览",
        "",
        f"- 数据集: `{payload.meta.get('dataset_path', '')}`",
        f"- 参与方: {', '.join(payload.meta.get('participants', []))}",
        f"- 合同数量: {payload.meta.get('contract_count', 0)}",
        f"- 条款对齐阈值: {payload.meta.get('clause_match_threshold', 0.0):.2f}",
        f"- 风险点匹配阈值: {payload.meta.get('risk_match_threshold', 0.0):.2f}",
        f"- 告警数: {len(payload.warnings)}",
        "",
        "> 说明：v2 刻意弱化了“文本完全一致就高分”的旧逻辑，更强调条款筛查、风险点枚举和建议是否可执行。",
        "",
    ]

    if single_contract:
        source_files = single_contract.get("source_files") or {}
        lines.extend(
            [
                "## 当前合同",
                "",
                f"- 合同 ID: `{single_contract.get('contract_id', '')}`",
                f"- 原合同 Markdown: `{source_files.get('original_md', '')}`",
                f"- 原合同源文件: `{source_files.get('original_doc', '')}`",
                f"- 采纳说明 Markdown: `{source_files.get('adoption_md', '')}`",
                "",
            ]
        )

    for policy, items in grouped.items():
        lines.extend(
            [
                f"## {_policy_name(policy)}",
                "",
                "| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in sorted(items, key=lambda value: value.participant):
            lines.append(
                "| {participant} | {cp} | {cr} | {cf} | {rp} | {rr} | {rf} | {matched} | {pred} | {gold} | {exp} | {sug} | {title} | {sug_overlap} |".format(
                    participant=item.participant,
                    cp=_pct(item.clause_metrics.precision),
                    cr=_pct(item.clause_metrics.recall),
                    cf=_pct(item.clause_metrics.f1),
                    rp=_pct(item.risk_metrics.precision),
                    rr=_pct(item.risk_metrics.recall),
                    rf=_pct(item.risk_metrics.f1),
                    matched=item.matched_pairs,
                    pred=item.predicted_risk_count,
                    gold=item.gold_risk_count,
                    exp=_pct(item.explanation_structure_score),
                    sug=_pct(item.suggestion_actionability_score),
                    title=_pct(item.exact_title_overlap),
                    sug_overlap=_pct(item.exact_suggestion_overlap),
                )
            )
        lines.append("")

    lines.extend(["## 使用提醒", ""])
    lines.extend(
        [
            "- `Exact Title Overlap` 或 `Exact Suggestion Overlap` 很高时，说明该参与方与标签可能存在同源文本风险。",
            "- `Suggestion Actionability` 低并不一定表示方向错误，也可能只是没有给出具体可执行建议。",
            "- 当前结果适合作为联调和直觉验证，不适合作为严格能力排行榜。",
            "",
            "## 告警",
            "",
        ]
    )
    if payload.warnings:
        for warning in payload.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def write_reports(output_dir: Path, payload: EvaluationPayload) -> dict[str, str]:
    """写入评估产物。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation_result.json"
    md_path = output_dir / "evaluation_report.md"

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

    write_text(md_path, render_markdown_report(payload))
    return {"json": str(json_path), "markdown": str(md_path)}
