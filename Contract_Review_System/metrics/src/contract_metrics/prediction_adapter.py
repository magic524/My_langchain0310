from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .baseline_parser import parse_baseline_markdown
from .text_utils import compact_text
from .types import ParticipantPrediction, RiskEntry


def _pick_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = compact_text(str(value))
        if text:
            return text
    return ""


def _extract_risk_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("risks", "items", "records", "predictions", "outputs"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if payload:
        return [payload]
    return []


def _parse_risk_item(contract_id: str, item: dict[str, Any], index: int, prefix: str) -> RiskEntry | None:
    has_risk = item.get("has_risk")
    if isinstance(has_risk, bool) and not has_risk:
        return None

    title = _pick_text(item, ("title", "risk_title", "risk_point", "name"))
    clause_text = _pick_text(item, ("clause_text", "clause", "条款原文", "original_clause"))
    explanation = _pick_text(item, ("explanation", "问题说明", "risk_reason", "analysis"))
    suggestion = _pick_text(item, ("suggestion", "建议修改", "proposal", "revision"))
    source_excerpt = _pick_text(item, ("source_excerpt", "raw_text", "evidence"))

    if not any([title, clause_text, explanation, suggestion]):
        return None

    return RiskEntry(
        risk_id=f"{contract_id}_{prefix}_{index:03d}",
        contract_id=contract_id,
        title=title or f"risk_{index}",
        clause_text=clause_text,
        explanation=explanation,
        suggestion=suggestion,
        source_excerpt=source_excerpt,
    )


def _parse_json_contract_block(
    contract_block: dict[str, Any],
    *,
    fallback_contract_id: str,
    prefix: str,
) -> ParticipantPrediction:
    contract_id = compact_text(str(contract_block.get("contract_id", ""))) or fallback_contract_id
    risk_items = _extract_risk_items(contract_block)

    risks: list[RiskEntry] = []
    for idx, item in enumerate(risk_items, start=1):
        parsed = _parse_risk_item(contract_id, item, idx, prefix)
        if parsed is not None:
            risks.append(parsed)

    return ParticipantPrediction(participant="agent", contract_id=contract_id, risks=risks)


def load_agent_predictions_from_json(
    *,
    json_path: Path,
    contract_ids: list[str],
) -> list[ParticipantPrediction]:
    """Load agent predictions from JSON path.

    Args:
        json_path: JSON file path.
        contract_ids: Known contract ids from dataset.

    Returns:
        Prediction list.
    """
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    blocks: list[dict[str, Any]] = []

    if isinstance(payload, dict) and isinstance(payload.get("contracts"), list):
        blocks = [item for item in payload["contracts"] if isinstance(item, dict)]
    elif isinstance(payload, list):
        blocks = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        blocks = [payload]

    if not blocks:
        return []

    default_contract_id = contract_ids[0] if len(contract_ids) == 1 else "unknown_contract"
    return [
        _parse_json_contract_block(block, fallback_contract_id=default_contract_id, prefix="json")
        for block in blocks
    ]


def _infer_contract_id_from_path(path: Path, contract_ids: list[str]) -> str:
    full = str(path)
    for contract_id in contract_ids:
        if contract_id in full:
            return contract_id
    if len(contract_ids) == 1:
        return contract_ids[0]
    return "unknown_contract"


def _infer_contract_id_from_content(text: str, contract_ids: list[str]) -> str:
    for contract_id in contract_ids:
        if contract_id in text:
            return contract_id
    if len(contract_ids) == 1:
        return contract_ids[0]
    return "unknown_contract"


def _parse_v1_clause_blocks(contract_id: str, markdown_text: str) -> list[RiskEntry]:
    pattern = re.compile(
        r"###\s*条款\s*(?P<idx>\d+)(?P<body>.*?)(?=\n###\s*条款|\Z)",
        flags=re.DOTALL,
    )

    clause_pattern = re.compile(r"原文摘录：\s*\n\s*>\s*(?P<clause>.+)")
    risk_level_pattern = re.compile(r"风险级别[:：]\s*(?P<risk_level>.+)")
    explanation_pattern = re.compile(r"问题说明[:：]\s*(?P<explanation>.+)")
    comment_pattern = re.compile(r"审查批注[:：]\s*(?P<comment>.+)")
    suggestion_pattern = re.compile(r"建议修改[:：]\s*(?P<suggestion>.+)")

    risks: list[RiskEntry] = []
    for matched in pattern.finditer(markdown_text):
        index = int(matched.group("idx"))
        body = matched.group("body")

        clause_match = clause_pattern.search(body)
        risk_level_match = risk_level_pattern.search(body)
        explanation_match = explanation_pattern.search(body)
        comment_match = comment_pattern.search(body)
        suggestion_match = suggestion_pattern.search(body)

        clause_text = compact_text(clause_match.group("clause")) if clause_match else ""
        risk_level = compact_text(risk_level_match.group("risk_level")) if risk_level_match else ""
        explanation = compact_text(explanation_match.group("explanation")) if explanation_match else ""
        review_comment = compact_text(comment_match.group("comment")) if comment_match else ""
        suggestion = compact_text(suggestion_match.group("suggestion")) if suggestion_match else ""
        merged_explanation = compact_text(" ".join(value for value in [explanation, review_comment] if value))

        if not any([clause_text, merged_explanation, suggestion]):
            continue

        risks.append(
            RiskEntry(
                risk_id=f"{contract_id}_agent_clause_{index:03d}",
                contract_id=contract_id,
                title=f"条款{index}({risk_level})" if risk_level else f"条款{index}",
                clause_text=clause_text,
                explanation=merged_explanation,
                suggestion=suggestion,
                source_excerpt=compact_text(body[:240]),
            )
        )

    return risks


def _parse_single_markdown(path: Path, contract_ids: list[str]) -> ParticipantPrediction:
    markdown_text = path.read_text(encoding="utf-8")
    contract_id = _infer_contract_id_from_path(path, contract_ids)
    if contract_id == "unknown_contract":
        contract_id = _infer_contract_id_from_content(markdown_text, contract_ids)

    risks = _parse_v1_clause_blocks(contract_id, markdown_text)
    risks.extend(
        parse_baseline_markdown(
            contract_id=contract_id,
            participant="agent",
            markdown_path=path,
        )
    )
    return ParticipantPrediction(participant="agent", contract_id=contract_id, risks=risks)


def load_agent_predictions_from_markdown(
    *,
    markdown_path: Path,
    contract_ids: list[str],
) -> list[ParticipantPrediction]:
    """Load agent predictions from markdown file or directory.

    Args:
        markdown_path: Markdown file or directory.
        contract_ids: Known contract ids from dataset.

    Returns:
        Prediction list.
    """
    if markdown_path.is_file():
        return [_parse_single_markdown(markdown_path, contract_ids)]

    paths = sorted(markdown_path.rglob("*.md"))
    return [_parse_single_markdown(path, contract_ids) for path in paths]


def merge_prediction_blocks(blocks: list[ParticipantPrediction]) -> list[ParticipantPrediction]:
    """Merge multiple prediction blocks by contract id.

    Args:
        blocks: Prediction blocks.

    Returns:
        Merged blocks.
    """
    by_contract: dict[str, list[RiskEntry]] = {}
    for block in blocks:
        by_contract.setdefault(block.contract_id, []).extend(block.risks)

    merged: list[ParticipantPrediction] = []
    for contract_id, risks in sorted(by_contract.items()):
        merged.append(
            ParticipantPrediction(
                participant="agent",
                contract_id=contract_id,
                risks=risks,
            )
        )
    return merged
