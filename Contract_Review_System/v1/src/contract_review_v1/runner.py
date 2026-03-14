from __future__ import annotations

import json
import re
from typing import Any

import requests

from .agent_core import SYSTEM_PROMPT, sanitize_review_text
from .schema import ParsedReview


BUSINESS_REVIEW_PROMPT = (
    "你将扮演一名经验丰富的专业合同审查律师。帮我审核一份原始合同，在审查过程中，你需要运用并体现以下核心审核能力：\n\n"
    "合规性审核：审查合同内容是否符合涉及的法律法规，确保合同的合法性及可执行性。并给出法律法规依据并指出风险点；\n\n"
    "风险识别与评估：精准识别合同中可能损害甲方利益的条款，特别是关于权利不对等、义务模糊、责任豁免、违约追责困难等核心风险点，"
    "并评估其潜在影响，以及对方主体风险（如涉诉情况、企业存续状态等）。请在结论中按“核心权益风险、财务风险、履约风险、解约风险”等类别进行摘要；\n\n"
    "文本严谨性审核：审查合同文本的准确性、逻辑性及一致性，修正错别字、语病、指代不明、标点误用等问题，消除因文本歧义可能引发的法律纠纷。"
)


OUTPUT_FORMAT_PROMPT_TEMPLATE = (
    "注意：当前仅审查一个目标条款，不是整份合同。请所有判断都围绕该条款给出。\n\n"
    "输出规则（必须严格遵守，便于系统评测解析）：\n"
    "- 若无明显风险，仅输出：无需批注\n"
    "- 若有风险，必须使用以下字段，字段名不要改动：\n"
    "风险级别：高 / 中 / 低\n"
    "问题说明：1-3 句，给出风险与影响\n"
    "审查批注：可直接给业务或法务；可在此处加入风险分类摘要\n"
    "建议修改：给出可执行改写文本\n"
    "参考依据：法律规则、交易惯例或“参考不足”\n\n"
    "目标条款：\n{clause_text}\n"
)


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
    runtime_config: Any,
) -> ParsedReview:
    """Generate prompt-only system review for one clause.

    Args:
        clause_text: Clause text to review.
        runtime_config: Runtime model config from configure_runtime_env.

    Returns:
        Parsed structured review.
    """

    # human_prompt = (
    #     "请仅参考下列目标条款，用审查助手的口吻给出批注式审查结果。输出要遵循：\n\n"
    #     "主要语言使用：中文\n"
    #     "风险级别：高 / 中 / 低\n"
    #     "问题说明：1-3 句\n"
    #     "审查批注：可直接给业务或法务\n"
    #     "建议修改：必要时给替换文本\n"
    #     "参考依据：如果无法判断则写 '参考不足'\n\n"
    #     f"目标条款：\n{clause_text}\n"
    # )

    # 双层提示词：SYSTEM_PROMPT 负责全局风格与安全约束，
    # BUSINESS_REVIEW_PROMPT 负责业务审核策略，
    # OUTPUT_FORMAT_PROMPT_TEMPLATE 负责单条款输入与结构化输出契约。
    strategy_prompt = BUSINESS_REVIEW_PROMPT
    format_prompt = OUTPUT_FORMAT_PROMPT_TEMPLATE.format(clause_text=clause_text)

    response = _send_chat_http(
        runtime_config,
        [
            ("system", SYSTEM_PROMPT),
            ("user", strategy_prompt),
            ("user", format_prompt),
        ],
    )
    raw_text = _extract_response_text(response)
    cleaned_text = sanitize_review_text(raw_text)
    return parse_review_text(cleaned_text)
