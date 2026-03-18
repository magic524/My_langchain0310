"""Two-stage global-context prompt runner.

Stage 1: Full contract → global risk scan (overall summary + high-risk clause id list).
Stage 2: Per-clause review with Stage 1 context injected into every prompt.

Output markdown format is identical to ``prompt_runner._render_agent_markdown`` so
the same evaluation pipeline (``evaluator`` / ``reporter``) can compare both approaches
directly.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .prompt_runner import (
    PromptRuntimeConfig,
    _extract_first_json,
    _send_chat,
    load_prompt_runtime_config,
    runtime_config_snapshot,
)
from .types import ContractDataset

# ---------------------------------------------------------------------------
# Stage 1: Global scan prompts
# ---------------------------------------------------------------------------

_GLOBAL_SCAN_SYSTEM = (
    "你是一名专业合同法律审查助手，擅长识别合同中的权利义务失衡、关键条款缺失、"
    "模糊表述和潜在争议风险。请仅输出一个 JSON 对象，不要附加任何说明文字。"
)

_GLOBAL_SCAN_USER_TMPL = """\
以下是合同全文（按条款 ID 拆分），请整体阅读后识别主要风险，输出一个 JSON 对象。

字段说明：
- risk_summary (string)：整体风险简评，100 字以内，指出最突出的 2-3 个问题。
- overall_balance (string)："balanced" / "party_a_favored" / "party_b_favored" / "unclear"。
- risky_clause_ids (list[string])：你认为存在法律或商业风险的条款 ID 列表（仅列 ID，不做解释）。

contract_id: {contract_id}

合同全文（条款列表）：
{contract_text}
"""

# ---------------------------------------------------------------------------
# Stage 2: Per-clause review with context prompts
# ---------------------------------------------------------------------------

_CLAUSE_REVIEW_SYSTEM = (
    "你是一名专业合同法律审查助手。"
    "请仅输出一个 JSON 对象，不要附加任何说明文字。"
)

_CLAUSE_REVIEW_USER_TMPL = """\
请结合以下全局审查背景，对当前单条款作出精确风险判断。

[全局审查背景]
合同 ID: {contract_id}
整体风险概要: {risk_summary}
权利义务平衡: {overall_balance}
预判高风险条款 ID: {risky_clause_ids}

[当前待审查条款]
clause_id: {clause_id}
clause_text: {clause_text}

请判断当前条款是否存在法律或商业风险，输出 JSON。
字段：has_risk(boolean), risk_level(string), title(string), explanation(string), suggestion(string)
规则：
1) has_risk=false 时其余字段可为空字符串。
2) has_risk=true 时 title/explanation/suggestion 均须具体填写。
3) suggestion 应为可操作的条款修改指引或补充措辞。
"""

_MAX_CONTRACT_CHARS = 12000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_contract_text(clauses: list[Any]) -> str:
    """Concatenate clauses into a single enumerated block for Stage 1."""
    parts = [f"[{clause.clause_id}]\n{clause.clause_text}" for clause in clauses]
    text = "\n\n".join(parts)
    if len(text) > _MAX_CONTRACT_CHARS:
        text = text[:_MAX_CONTRACT_CHARS] + "\n...(内容过长，已截断)"
    return text


def _global_scan_contract(
    *,
    runtime: PromptRuntimeConfig,
    contract_id: str,
    clauses: list[Any],
) -> dict[str, Any]:
    """Stage 1: send full contract, get global risk context.

    Args:
        runtime: LLM runtime config.
        contract_id: Contract identifier.
        clauses: Clause list from dataset.

    Returns:
        Dict with ``risk_summary``, ``overall_balance``, ``risky_clause_ids``.
    """
    contract_text = _build_contract_text(clauses)
    user_prompt = _GLOBAL_SCAN_USER_TMPL.format(
        contract_id=contract_id,
        contract_text=contract_text,
    )
    raw = _send_chat(runtime, system_prompt=_GLOBAL_SCAN_SYSTEM, user_prompt=user_prompt)
    parsed = _extract_first_json(raw)

    risky_ids = parsed.get("risky_clause_ids")
    if not isinstance(risky_ids, list):
        risky_ids = []

    return {
        "risk_summary": str(parsed.get("risk_summary", "")).strip(),
        "overall_balance": str(parsed.get("overall_balance", "unclear")).strip(),
        "risky_clause_ids": [str(cid) for cid in risky_ids],
    }


def _review_clause_with_context(
    *,
    runtime: PromptRuntimeConfig,
    contract_id: str,
    clause_id: str,
    clause_text: str,
    global_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Stage 2: per-clause review with global context injected.

    Args:
        runtime: LLM runtime config.
        contract_id: Contract identifier.
        clause_id: Clause identifier.
        clause_text: Clause text content.
        global_ctx: Output from ``_global_scan_contract``.

    Returns:
        Dict with ``has_risk``, ``risk_level``, ``title``, ``explanation``, ``suggestion``.
    """
    risky_ids = global_ctx.get("risky_clause_ids") or []
    ids_str = "、".join(risky_ids) if risky_ids else "（无）"

    user_prompt = _CLAUSE_REVIEW_USER_TMPL.format(
        contract_id=contract_id,
        risk_summary=global_ctx.get("risk_summary", ""),
        overall_balance=global_ctx.get("overall_balance", "unclear"),
        risky_clause_ids=ids_str,
        clause_id=clause_id,
        clause_text=clause_text,
    )
    raw = _send_chat(runtime, system_prompt=_CLAUSE_REVIEW_SYSTEM, user_prompt=user_prompt)
    parsed = _extract_first_json(raw)

    if not parsed:
        return {
            "has_risk": False,
            "risk_level": "",
            "title": "",
            "explanation": "",
            "suggestion": "",
        }
    return {
        "has_risk": bool(parsed.get("has_risk", False)),
        "risk_level": str(parsed.get("risk_level", "")).strip(),
        "title": str(parsed.get("title", "")).strip(),
        "explanation": str(parsed.get("explanation", "")).strip(),
        "suggestion": str(parsed.get("suggestion", "")).strip(),
    }


def _render_agent_markdown(results: list[tuple[str, str, dict[str, Any], str]]) -> str:
    """Render results to markdown.

    Format is identical to ``prompt_runner._render_agent_markdown`` so the
    evaluation pipeline (``prediction_adapter``) can parse both outputs the
    same way.

    Args:
        results: List of ``(contract_id, clause_id, review_dict, clause_text)``.

    Returns:
        Markdown string.
    """
    lines: list[str] = ["# Global-Context Contract Review Report", ""]
    current_contract = ""
    index = 0

    for contract_id, clause_id, review, clause_text in results:
        if contract_id != current_contract:
            current_contract = contract_id
            lines.append(f"## Contract: {contract_id}")
            lines.append("")
        if not review.get("has_risk", False):
            continue

        index += 1
        risk_level = str(review.get("risk_level", "")).strip() or "medium"
        title = str(review.get("title", "")).strip() or f"{clause_id} risk"
        explanation = str(review.get("explanation", "")).strip()
        suggestion = str(review.get("suggestion", "")).strip()

        lines.append(f"### Clause {index}")
        lines.append(f"- Clause ID: {clause_id}")
        lines.append(f"- Risk Level: {risk_level}")
        lines.append(f"- Risk Title: {title}")
        lines.append("- Clause Text:")
        lines.append(f"  > {clause_text}")
        lines.append(f"- Explanation: {explanation}")
        lines.append(f"- Suggestion: {suggestion}")
        lines.append("")

    if index == 0:
        lines.append("No risky clauses detected.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_global_prompt_review(
    *,
    contracts: list[ContractDataset],
    output_markdown_path: Path,
) -> tuple[Path, int, dict[str, Any]]:
    """Two-stage global-context clause review.

    For each contract:
      - Stage 1: send full contract text to LLM and obtain a global risk
        context (summary, balance judgment, high-risk clause id list).
      - Stage 2: review each clause individually, with Stage 1 context
        injected into every prompt so the model can reason across clauses.

    Output markdown format is identical to ``run_prompt_only_review`` so
    the results can be fed directly into the same evaluation pipeline.

    Args:
        contracts: Parsed dataset contracts.
        output_markdown_path: Output markdown file path.

    Returns:
        Tuple of ``(output_markdown_path, risk_count, runtime_snapshot)``.
    """
    runtime = load_prompt_runtime_config()

    reviewed: list[tuple[str, str, dict[str, Any], str]] = []
    risk_count = 0

    for contract in contracts:
        print(f"  [Stage 1 / 全局扫描] {contract.contract_id} ...")
        global_ctx = _global_scan_contract(
            runtime=runtime,
            contract_id=contract.contract_id,
            clauses=contract.clauses,
        )
        risky_ids_hint = global_ctx.get("risky_clause_ids") or []
        print(f"  [Stage 1 完成] 整体平衡={global_ctx.get('overall_balance')}，"
              f"预判高风险条款 {len(risky_ids_hint)} 个: {risky_ids_hint}")
        print(f"  [Stage 2 / 逐条款精审] {contract.contract_id}，共 {len(contract.clauses)} 条 ...")

        for clause in contract.clauses:
            review = _review_clause_with_context(
                runtime=runtime,
                contract_id=contract.contract_id,
                clause_id=clause.clause_id,
                clause_text=clause.clause_text,
                global_ctx=global_ctx,
            )
            if review.get("has_risk", False):
                risk_count += 1
            reviewed.append((contract.contract_id, clause.clause_id, review, clause.clause_text))

    output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_markdown_path.write_text(_render_agent_markdown(reviewed), encoding="utf-8")
    return output_markdown_path, risk_count, runtime_config_snapshot(runtime)
