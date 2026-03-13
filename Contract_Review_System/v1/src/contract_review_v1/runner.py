from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

from .schema import ParsedReview


def load_agent_module(agent_module_path: Path) -> Any:
    """Load the existing contract review module for prompt and env config reuse.

    Args:
        agent_module_path: Path to the existing contract_review_agent.py file.

    Returns:
        Imported python module object.
    """

    spec = importlib.util.spec_from_file_location("contract_review_agent", str(agent_module_path))
    if spec is None or spec.loader is None:
        msg = f"Cannot load module: {agent_module_path}"
        raise RuntimeError(msg)

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _send_chat_http(config: Any, messages: list[tuple[str, str]]) -> dict[str, Any]:
    if not config.base_url:
        msg = "OPENAI_API_BASE is required for prompt-only evaluation"
        raise RuntimeError(msg)

    url = config.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key and config.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload: dict[str, Any] = {
        "model": config.model_name,
        "messages": [{"role": role, "content": content} for role, content in messages],
        "temperature": float(config.temperature),
    }
    if getattr(config, "extra_body", None):
        payload.update(config.extra_body)

    response = requests.post(url, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()


def _extract_response_text(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not choices:
        return json.dumps(response, ensure_ascii=False)

    first = choices[0]
    if not isinstance(first, dict):
        return str(first)

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content

    text = first.get("text")
    if isinstance(text, str):
        return text

    return json.dumps(response, ensure_ascii=False)


def parse_review_text(raw_text: str) -> ParsedReview:
    """Parse model output into structured fields.

    Args:
        raw_text: Raw model output text.

    Returns:
        Parsed review object used by evaluator.
    """

    text = raw_text.strip()
    if not text:
        return ParsedReview(False, None, [], "", "", raw_text)

    if "无需批注" in text:
        return ParsedReview(False, None, [], "", "", raw_text)

    def extract(label: str) -> str:
        pattern = rf"{label}\s*[:：]\s*(.+?)(?=\n\S+\s*[:：]|\Z)"
        match = re.search(pattern, text, flags=re.DOTALL)
        return match.group(1).strip() if match else ""

    risk_level = extract("风险级别") or None
    explanation = extract("问题说明")
    suggestion = extract("建议修改")

    reference_basis = extract("参考依据")
    risk_points: list[str] = []
    for candidate in re.split(r"[；;，,\n]", reference_basis):
        compact = candidate.strip()
        if compact and compact != "参考不足":
            risk_points.append(compact)

    return ParsedReview(
        has_risk=True,
        risk_level=risk_level,
        risk_points=risk_points,
        explanation=explanation,
        suggestion=suggestion,
        raw_text=raw_text.strip(),
    )


def generate_system_review(
    clause_text: str,
    *,
    agent_module: Any,
    runtime_config: Any,
) -> ParsedReview:
    """Generate prompt-only system review for one clause.

    Args:
        clause_text: Clause text to review.
        agent_module: Loaded module that contains SYSTEM_PROMPT and sanitizer.
        runtime_config: Runtime model config from configure_runtime_env.

    Returns:
        Parsed structured review.
    """

    human_prompt = (
        "请仅参考下列目标条款，用审查助手的口吻给出批注式审查结果。输出要遵循：\n\n"
        "主要语言使用：中文\n"
        "风险级别：高 / 中 / 低\n"
        "问题说明：1-3 句\n"
        "审查批注：可直接给业务或法务\n"
        "建议修改：必要时给替换文本\n"
        "参考依据：如果无法判断则写 '参考不足'\n\n"
        f"目标条款：\n{clause_text}\n"
    )

    response = _send_chat_http(
        runtime_config,
        [("system", agent_module.SYSTEM_PROMPT), ("user", human_prompt)],
    )
    raw_text = _extract_response_text(response)
    cleaned_text = agent_module.sanitize_review_text(raw_text)
    return parse_review_text(cleaned_text)
