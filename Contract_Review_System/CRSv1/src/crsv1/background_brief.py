from __future__ import annotations

import json
from typing import Any

from .runtime_types import ContractBackgroundBrief
from .text_utils import short_preview


def _extract_last_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    if "</think>" in stripped:
        stripped = stripped.split("</think>")[-1].strip()
    decoder = json.JSONDecoder()
    brace_indexes = [index for index, char in enumerate(stripped) if char == "{"]
    for start in reversed(brace_indexes):
        candidate = stripped[start:]
        try:
            payload, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def parse_background_brief(raw_text: str, contract_text: str) -> ContractBackgroundBrief:
    """Parse background JSON, falling back to lightweight heuristics."""

    payload = _extract_last_json_object(raw_text)
    if not payload:
        first_nonempty_lines = [line.strip() for line in contract_text.splitlines() if line.strip()]
        preview = " / ".join(first_nonempty_lines[:3])
        return ContractBackgroundBrief(
            contract_type=first_nonempty_lines[0] if first_nonempty_lines else "未识别合同类型",
            transaction_purpose=short_preview(preview, limit=120),
            parties_summary="模型未返回标准背景摘要，已使用合同前文作为回退。",
            performance_path=[],
            high_risk_topics=[],
            review_focus=[],
            search_hints=[],
            raw_response_excerpt=raw_text[:240].strip(),
        )

    def _list_value(key: str) -> list[str]:
        value = payload.get(key, [])
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    return ContractBackgroundBrief(
        contract_type=str(payload.get("contract_type", "")).strip(),
        transaction_purpose=str(payload.get("transaction_purpose", "")).strip(),
        parties_summary=str(payload.get("parties_summary", "")).strip(),
        performance_path=_list_value("performance_path"),
        high_risk_topics=_list_value("high_risk_topics"),
        review_focus=_list_value("review_focus"),
        search_hints=_list_value("search_hints"),
        raw_response_excerpt=raw_text[:240].strip(),
    )
