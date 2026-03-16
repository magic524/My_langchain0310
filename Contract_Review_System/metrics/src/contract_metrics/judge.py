from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import find_dotenv, load_dotenv

from .text_utils import contains_any, text_similarity, token_overlap_ratio
from .types import RiskEntry


@dataclass(slots=True)
class JudgeThresholds:
    """Thresholds used by rule-based judge."""

    direction_consistency_threshold: float
    explanation_accuracy_threshold: float
    suggestion_accuracy_threshold: float


@dataclass(slots=True)
class LLMRuntimeConfig:
    """OpenAI-compatible HTTP runtime config."""

    model_name: str
    api_key: str
    base_url: str
    temperature: float
    extra_body: dict[str, Any] | None


def _parse_json_env(env_name: str) -> dict[str, Any] | None:
    raw_value = os.getenv(env_name)
    if not raw_value:
        return None
    loaded = json.loads(raw_value)
    if isinstance(loaded, dict):
        return loaded
    return None


def load_llm_runtime_config() -> LLMRuntimeConfig:
    """Load LLM judge runtime from environment variables.

    Returns:
        Runtime config.

    Raises:
        RuntimeError: If base URL is missing.
    """
    load_dotenv(find_dotenv(usecwd=True))

    model_name = (
        os.getenv("OPENAI_LLM_MODEL")
        or os.getenv("OPENAI_MODEL_NAME")
        or os.getenv("OPENAI_MODEL")
        or "qwen-plus"
    )
    base_url = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY") or "EMPTY"
    temp_raw = os.getenv("OPENAI_TEMPERATURE", "0.0")
    extra_body = _parse_json_env("OPENAI_EXTRA_BODY")

    if not base_url:
        msg = "OPENAI_API_BASE / OPENAI_BASE_URL is required for LLM judge"
        raise RuntimeError(msg)

    try:
        temperature = float(temp_raw)
    except ValueError:
        temperature = 0.0

    return LLMRuntimeConfig(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        extra_body=extra_body,
    )


def _has_clause_quote(label_clause: str, pred_clause: str, pred_explanation: str) -> float:
    if not label_clause:
        return 0.0
    if text_similarity(label_clause, pred_clause) >= 0.3:
        return 1.0

    compact = re.sub(r"\s+", "", label_clause)
    if len(compact) >= 10:
        probe = compact[:10]
        if probe and probe in re.sub(r"\s+", "", pred_explanation):
            return 1.0
    return 0.0


def rule_explanation_scores(
    *,
    label: RiskEntry,
    prediction: RiskEntry,
    thresholds: JudgeThresholds,
) -> dict[str, float]:
    """Rule-based explanation scoring.

    Args:
        label: Label risk entry.
        prediction: Participant prediction entry.
        thresholds: Rule thresholds.

    Returns:
        Score dictionary with direction/accuracy/completeness.
    """
    direction_signal = max(
        token_overlap_ratio(
            f"{prediction.title} {prediction.explanation}",
            f"{label.title} {label.explanation}",
        ),
        text_similarity(prediction.explanation, label.explanation),
    )
    direction = 1.0 if direction_signal >= thresholds.direction_consistency_threshold else 0.0

    accuracy = text_similarity(prediction.explanation, label.explanation)

    risk_type_ok = 1.0 if token_overlap_ratio(prediction.title, label.title) >= 0.2 else 0.0
    reason_ok = 1.0 if contains_any(prediction.explanation, ("原因", "由于", "因为", "存在", "未", "不明确")) else 0.0
    clause_ok = _has_clause_quote(label.clause_text, prediction.clause_text, prediction.explanation)
    consequence_ok = 1.0 if contains_any(prediction.explanation, ("导致", "可能", "风险", "损失", "责任", "后果")) else 0.0
    completeness = (risk_type_ok + reason_ok + clause_ok + consequence_ok) / 4.0

    return {
        "direction_consistency": direction,
        "accuracy": accuracy,
        "completeness": completeness,
    }


def rule_suggestion_scores(
    *,
    label: RiskEntry,
    prediction: RiskEntry,
    thresholds: JudgeThresholds,
) -> dict[str, float]:
    """Rule-based suggestion scoring.

    Args:
        label: Label risk entry.
        prediction: Participant prediction entry.
        thresholds: Rule thresholds.

    Returns:
        Score dictionary with direction/content_accuracy/completeness.
    """
    direction_signal = max(
        token_overlap_ratio(
            f"{prediction.suggestion} {prediction.title}",
            f"{label.title} {label.suggestion} {label.explanation}",
        ),
        text_similarity(prediction.suggestion, label.suggestion),
    )
    direction = 1.0 if direction_signal >= thresholds.direction_consistency_threshold else 0.0

    content_accuracy = text_similarity(prediction.suggestion, label.suggestion)

    coverage = token_overlap_ratio(prediction.suggestion, label.suggestion)
    actionable = 1.0 if contains_any(prediction.suggestion, ("建议", "应", "应当", "修改", "补充", "删除", "明确", "增加", "调整")) else 0.0
    clause_bind = _has_clause_quote(label.clause_text, prediction.clause_text, prediction.suggestion)
    completeness = (coverage + actionable + clause_bind) / 3.0

    return {
        "direction_consistency": direction,
        "content_accuracy": content_accuracy,
        "completeness": completeness,
    }


def _send_llm_chat(runtime: LLMRuntimeConfig, prompt: str) -> str:
    url = runtime.base_url.rstrip("/") + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if runtime.api_key and runtime.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {runtime.api_key}"

    payload: dict[str, Any] = {
        "model": runtime.model_name,
        "messages": [
            {"role": "system", "content": "你是合同审查评测裁判。只返回 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": runtime.temperature,
    }
    if runtime.extra_body:
        payload.update(runtime.extra_body)

    response = requests.post(url, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        return "{}"
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "{}"


def _parse_llm_scores(raw_text: str, keys: tuple[str, ...]) -> dict[str, float]:
    matched = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if not matched:
        return {key: 0.0 for key in keys}

    try:
        payload = json.loads(matched.group(0))
    except json.JSONDecodeError:
        return {key: 0.0 for key in keys}

    scores: dict[str, float] = {}
    for key in keys:
        value = payload.get(key, 0.0)
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.0
        scores[key] = max(0.0, min(1.0, score))
    return scores


def llm_explanation_scores(runtime: LLMRuntimeConfig, *, label: RiskEntry, prediction: RiskEntry) -> dict[str, float]:
    """LLM-based explanation scoring."""
    prompt = (
        "请比较标签解释与预测解释，并只输出 JSON。\n"
        "字段：direction_consistency, accuracy, completeness，范围 0~1。\n"
        f"标签标题：{label.title}\n"
        f"标签条款：{label.clause_text}\n"
        f"标签解释：{label.explanation}\n"
        f"预测标题：{prediction.title}\n"
        f"预测条款：{prediction.clause_text}\n"
        f"预测解释：{prediction.explanation}\n"
    )
    raw = _send_llm_chat(runtime, prompt)
    return _parse_llm_scores(raw, ("direction_consistency", "accuracy", "completeness"))


def llm_suggestion_scores(runtime: LLMRuntimeConfig, *, label: RiskEntry, prediction: RiskEntry) -> dict[str, float]:
    """LLM-based suggestion scoring."""
    prompt = (
        "请比较标签建议与预测建议，并只输出 JSON。\n"
        "字段：direction_consistency, content_accuracy, completeness，范围 0~1。\n"
        f"标签标题：{label.title}\n"
        f"标签条款：{label.clause_text}\n"
        f"标签建议：{label.suggestion}\n"
        f"预测标题：{prediction.title}\n"
        f"预测条款：{prediction.clause_text}\n"
        f"预测建议：{prediction.suggestion}\n"
    )
    raw = _send_llm_chat(runtime, prompt)
    return _parse_llm_scores(raw, ("direction_consistency", "content_accuracy", "completeness"))
