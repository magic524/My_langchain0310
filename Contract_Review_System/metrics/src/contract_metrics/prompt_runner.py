from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import find_dotenv, load_dotenv

from .types import ContractDataset, RiskEntry


@dataclass(slots=True)
class PromptRuntimeConfig:
    """OpenAI-compatible runtime config for prompt-only review."""

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


def _load_env_files() -> None:
    """Load `.env` files with deterministic priority.

    Priority:
    1) `Contract_Review_System/metrics/.env`
    2) nearest `.env` discovered from current working directory
    """
    metrics_root = Path(__file__).resolve().parents[2]
    metrics_env = metrics_root / ".env"
    if metrics_env.exists():
        load_dotenv(metrics_env, override=False)

    fallback_env = find_dotenv(usecwd=True)
    if fallback_env:
        load_dotenv(fallback_env, override=False)


def load_prompt_runtime_config() -> PromptRuntimeConfig:
    """Load prompt runtime config from `.env` and environment variables."""
    _load_env_files()

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
        msg = "OPENAI_API_BASE / OPENAI_BASE_URL is required for prompt-only generation"
        raise RuntimeError(msg)

    try:
        temperature = float(temp_raw)
    except ValueError:
        temperature = 0.0

    return PromptRuntimeConfig(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        extra_body=extra_body,
    )


def runtime_config_snapshot(runtime: PromptRuntimeConfig) -> dict[str, Any]:
    """Return a safe runtime snapshot for markdown/json logs."""
    api_key_masked = ""
    if runtime.api_key:
        if len(runtime.api_key) <= 6:
            api_key_masked = "***"
        else:
            api_key_masked = f"{runtime.api_key[:3]}***{runtime.api_key[-3:]}"

    return {
        "model_name": runtime.model_name,
        "base_url": runtime.base_url,
        "temperature": runtime.temperature,
        "extra_body": runtime.extra_body or {},
        "api_key_masked": api_key_masked or "(empty or EMPTY)",
    }


def _send_chat(runtime: PromptRuntimeConfig, *, system_prompt: str, user_prompt: str) -> str:
    url = runtime.base_url.rstrip("/") + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if runtime.api_key and runtime.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {runtime.api_key}"

    payload: dict[str, Any] = {
        "model": runtime.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": runtime.temperature,
    }
    if runtime.extra_body:
        payload.update(runtime.extra_body)

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        return "{}"
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "{}"


def _extract_first_json(text: str) -> dict[str, Any]:
    matched = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not matched:
        return {}
    try:
        loaded = json.loads(matched.group(0))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _review_single_clause(
    *,
    runtime: PromptRuntimeConfig,
    contract_id: str,
    clause_id: str,
    clause_text: str,
) -> dict[str, Any]:
    system_prompt = (
        "You are a contract risk review assistant. "
        "Return exactly one JSON object and no extra text."
    )
    user_prompt = (
        "Review whether the clause has legal or business risk and return JSON.\n"
        "Fields: has_risk(boolean), risk_level(string), title(string), "
        "explanation(string), suggestion(string).\n"
        "Rules:\n"
        "1) If has_risk=false, other fields can be empty strings.\n"
        "2) If has_risk=true, provide specific title/explanation/suggestion.\n"
        "3) Suggestion should be actionable clause revision guidance.\n\n"
        f"contract_id: {contract_id}\n"
        f"clause_id: {clause_id}\n"
        f"clause_text: {clause_text}\n"
    )

    raw = _send_chat(runtime, system_prompt=system_prompt, user_prompt=user_prompt)
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
    lines: list[str] = ["# Prompt-Only Contract Review Report", ""]
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


def run_prompt_only_review(
    *,
    contracts: list[ContractDataset],
    output_markdown_path: Path,
) -> tuple[Path, int, dict[str, Any]]:
    """Run prompt-only clause review and write markdown output.

    Args:
        contracts: Parsed dataset contracts.
        output_markdown_path: Output markdown file path.

    Returns:
        Tuple of `(output_markdown_path, risk_count, runtime_snapshot)`.
    """
    runtime = load_prompt_runtime_config()

    reviewed: list[tuple[str, str, dict[str, Any], str]] = []
    risk_count = 0
    for contract in contracts:
        for clause in contract.clauses:
            review = _review_single_clause(
                runtime=runtime,
                contract_id=contract.contract_id,
                clause_id=clause.clause_id,
                clause_text=clause.clause_text,
            )
            if review.get("has_risk", False):
                risk_count += 1
            reviewed.append((contract.contract_id, clause.clause_id, review, clause.clause_text))

    output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_markdown_path.write_text(_render_agent_markdown(reviewed), encoding="utf-8")
    return output_markdown_path, risk_count, runtime_config_snapshot(runtime)


def risks_from_rendered_markdown(markdown_path: Path) -> list[RiskEntry]:
    """Compatibility helper kept for possible future extension."""
    _ = markdown_path
    return []
