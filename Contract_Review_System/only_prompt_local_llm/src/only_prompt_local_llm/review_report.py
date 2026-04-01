from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_name(contract_id: str) -> str:
    return contract_id.replace("/", "_").replace("\\", "_").replace(":", "_")


def _normalize_cell(text: str) -> str:
    normalized = " ".join(str(text).split())
    if not normalized:
        return "-"
    return normalized.replace("|", "\\|")


def render_contract_review_report(contract: dict[str, Any]) -> str:
    """Render one customer-facing contract review report in Markdown."""

    contract_id = str(contract.get("contract_id", "")).strip() or "unknown-contract"
    source_files = contract.get("source_files") or {}
    risks = list((contract.get("participants") or {}).get("local_llm") or [])

    lines = [
        f"# {contract_id} 审查报告",
        "",
        "## 合同信息",
        "",
        f"- 原始合同: `{source_files.get('original_doc', '')}`",
        f"- 合同 Markdown: `{source_files.get('original_md', '')}`",
        f"- 风险点数量: `{len(risks)}`",
        "",
        "## 风险点表格",
        "",
    ]

    if not risks:
        lines.extend(
            [
                "当前未识别到明确风险点。",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "| 序号 | 风险点 | 对应条款 | 风险说明 | 修改建议 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for index, item in enumerate(risks, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _normalize_cell(item.get("title", "")),
                    _normalize_cell(item.get("clause_text", "")),
                    _normalize_cell(item.get("explanation", "")),
                    _normalize_cell(item.get("suggestion", "")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 结论",
            "",
            f"本次审查共识别 `{len(risks)}` 个风险点，请结合业务背景进一步确认修改优先级。",
            "",
        ]
    )
    return "\n".join(lines)


def export_review_reports(dataset_path: Path, output_dir: Path) -> dict[str, Any]:
    """Write Markdown review reports from a dataset with `local_llm` risks."""

    dataset_payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    contracts_summary: list[dict[str, str]] = []
    summary_lines = ["# 审查报告汇总", ""]

    for contract in dataset_payload.get("contracts", []):
        contract_id = str(contract.get("contract_id", "")).strip()
        if not contract_id:
            continue

        report_path = output_dir / f"{_safe_name(contract_id)}_审查报告.md"
        report_path.write_text(render_contract_review_report(contract), encoding="utf-8")
        contracts_summary.append(
            {
                "contract_id": contract_id,
                "report_path": str(report_path),
            }
        )
        summary_lines.append(f"- {contract_id}: `{report_path}`")

    summary_path = output_dir / "审查报告汇总.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return {
        "output_dir": str(output_dir),
        "summary_path": str(summary_path),
        "contracts": contracts_summary,
    }
