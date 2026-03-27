from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
CONTRACT_REVIEW_ROOT = CURRENT_FILE.parents[3]
PROJECT_ROOT = CURRENT_FILE.parents[4]
TESTS_ROOT = CONTRACT_REVIEW_ROOT / "tests"
SRC_ROOT = TESTS_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Contract_Review_System.common.local_llm_client import (
    RuntimeConfig,
    build_payload,
    post_chat_request,
)
from contract_tests.dataset_builder import build_dataset
from contract_tests.types import RiskItem


SYSTEM_PROMPT = """你是合同审查助手。

你会收到一整份合同的 markdown 全文。
你的任务是找出合同中的风险点，并输出严格 JSON。

要求：
1. 只输出 JSON，不要输出解释性前后缀。
2. 风险点要尽量绑定原合同中的具体条款原文。
3. explanation 要说明风险原因或不利后果。
4. suggestion 要给出可执行的修改建议。
5. 如果没有识别到风险，输出 {"risks": []}。
"""


USER_PROMPT_TEMPLATE = """请审查下面这份合同全文，并找出风险点。

输出格式必须是：
{{
  "risks": [
    {{
            "title": "风险标题",
            "clause_text": "对应的合同原文片段",
            "explanation": "风险原因或后果",
            "suggestion": "修改建议"
    }}
  ]
}}

注意：
- 这是整份合同全文输入，不要按段落逐段回答。
- `title` 要简洁明确。
- `clause_text` 尽量摘录原合同中的关键条款原文。
- `suggestion` 不要只写“建议完善”，要尽量写具体。

合同全文如下：
{contract_text}
"""


def send_chat_via_langchain(runtime: RuntimeConfig, messages: list[tuple[str, str]]) -> str:
    """Internal helper."""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = (
            "Missing `langchain_openai` or `langchain_core`. "
            "Please run this in the `langchain` conda environment or install the required packages."
        )
        raise RuntimeError(msg) from exc

    chat_model = ChatOpenAI(
        openai_api_key=runtime.api_key or "EMPTY",
        openai_api_base=runtime.base_url,
        model_name=runtime.model_name,
        temperature=runtime.temperature,
        extra_body=runtime.extra_body,
    )
    lc_messages = []
    for role, content in messages:
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    response = chat_model.invoke(lc_messages)
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict) and "text" in item:
                chunks.append(str(item["text"]))
        return "\n".join(part.strip() for part in chunks if part.strip()).strip()
    return str(content).strip()


def sanitize_payload_for_debug(payload: dict[str, Any]) -> dict[str, Any]:
    """Internal helper."""

    sanitized = deepcopy(payload)
    messages = sanitized.get("messages")
    if not isinstance(messages, list):
        return sanitized

    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        message["content_preview"] = content[:800]
        message["content_length"] = len(content)
        message.pop("content", None)
    return sanitized


def write_debug_payload(debug_path: Path, payload: dict[str, Any], *, note: str) -> None:
    """Internal helper."""

    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(
        json.dumps(
            {
                "note": note,
                "request": sanitize_payload_for_debug(payload),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def send_chat(
    runtime: RuntimeConfig,
    messages: list[tuple[str, str]],
    *,
    debug_path: Path | None = None,
) -> str:
    """Internal helper."""

    primary_payload = build_payload(runtime, messages, extra_body=runtime.extra_body)
    if debug_path is not None:
        write_debug_payload(debug_path, primary_payload, note="primary_request")

    try:
        return send_chat_via_langchain(runtime, messages)
    except RuntimeError as exc:
        primary_error = str(exc)
    except Exception as exc:  # noqa: BLE001
        primary_error = f"ChatOpenAI 调用失败: {exc}"

    if runtime.extra_body:
        fallback_payload = build_payload(runtime, messages, extra_body=None)
        if debug_path is not None:
            write_debug_payload(debug_path, fallback_payload, note="fallback_request_without_extra_body")
        try:
            fallback_runtime = RuntimeConfig(
                model_name=runtime.model_name,
                api_key=runtime.api_key,
                base_url=runtime.base_url,
                temperature=runtime.temperature,
                extra_body=None,
            )
            return send_chat_via_langchain(fallback_runtime, messages)
        except RuntimeError as fallback_exc:
            fallback_error = str(fallback_exc)
        except Exception as fallback_exc:  # noqa: BLE001
            fallback_error = f"ChatOpenAI 降级调用失败: {fallback_exc}"

        try:
            return post_chat_request(
                RuntimeConfig(
                    model_name=runtime.model_name,
                    api_key=runtime.api_key,
                    base_url=runtime.base_url,
                    temperature=runtime.temperature,
                    extra_body=None,
                ),
                fallback_payload,
            )
        except RuntimeError as raw_fallback_exc:
            raw_fallback_error = str(raw_fallback_exc)
            msg = (
                "Local model requests failed multiple times. "
                f"First attempt: {primary_error}. "
                f"Retry without OPENAI_EXTRA_BODY via ChatOpenAI: {fallback_error}. "
                f"Final raw HTTP fallback also failed: {raw_fallback_error}"
            )
            raise RuntimeError(msg) from raw_fallback_exc

    raise RuntimeError(primary_error)


def extract_json_block(text: str) -> dict[str, Any]:
    """Internal helper."""

    stripped = text.strip()
    if not stripped:
        return {"risks": []}

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
        if isinstance(payload, dict) and isinstance(payload.get("risks"), list):
            return payload

    return {"risks": []}


def extract_risk_dicts_by_lines(text: str) -> list[dict[str, str]]:
    """Internal helper."""

    marker = text.rfind('"risks"')
    if marker == -1:
        return []

    fields = ("title", "clause_text", "explanation", "suggestion")
    results: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for raw_line in text[marker:].splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line in {"{", "},", "}"}:
            if current:
                results.append(current)
                current = {}
            continue

        for field in fields:
            prefix = f'"{field}":'
            if not line.startswith(prefix):
                continue

            value_part = line[len(prefix) :].strip()
            if not value_part.startswith('"'):
                current[field] = value_part.rstrip(",").strip()
                break

            end_quote_index = value_part.rfind('"')
            if end_quote_index <= 0:
                current[field] = value_part[1:].rstrip(",").strip()
                break

            current[field] = value_part[1:end_quote_index]
            break

    if current:
        results.append(current)

    cleaned_results: list[dict[str, str]] = []
    for item in results:
        if not any(item.get(field, "").strip() for field in fields):
            continue
        cleaned_results.append({field: item.get(field, "").strip() for field in fields})
    return cleaned_results


def parse_local_risks(contract_id: str, raw_text: str) -> list[RiskItem]:
    """Internal helper."""

    payload = extract_json_block(raw_text)
    risks = payload.get("risks") or []
    if not isinstance(risks, list):
        risks = []
    if not risks:
        risks = extract_risk_dicts_by_lines(raw_text)
    if not isinstance(risks, list):
        return []

    results: list[RiskItem] = []
    for index, item in enumerate(risks, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        clause_text = str(item.get("clause_text", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        suggestion = str(item.get("suggestion", "")).strip()
        if not any([title, clause_text, explanation, suggestion]):
            continue
        results.append(
            RiskItem(
                risk_id=f"{contract_id}_local_llm_{index:03d}",
                contract_id=contract_id,
                title=title,
                clause_text=clause_text,
                explanation=explanation,
                suggestion=suggestion,
                source_excerpt=raw_text[:240].strip(),
            )
        )
    return results


def load_dataset_payload(dataset_path: Path) -> dict[str, Any]:
    """Internal helper."""

    return json.loads(dataset_path.read_text(encoding="utf-8"))


def filter_contracts(
    dataset_payload: dict[str, Any],
    *,
    contract_filter: str | None,
) -> dict[str, Any]:
    """Internal helper."""

    if not contract_filter:
        return dataset_payload

    contracts = dataset_payload.get("contracts", [])
    if not isinstance(contracts, list):
        msg = "dataset_payload['contracts'] must be a list."
        raise RuntimeError(msg)

    filtered_contracts = []
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        contract_id = str(contract.get("contract_id", "")).strip()
        if contract_filter in contract_id:
            filtered_contracts.append(contract)

    if not filtered_contracts:
        msg = f"未找到匹配合同: {contract_filter}"
        raise RuntimeError(msg)

    filtered_payload = dict(dataset_payload)
    filtered_payload["contracts"] = filtered_contracts
    return filtered_payload


def run_local_prediction(
    run_id: str,
    runtime: RuntimeConfig,
    *,
    output_dir: Path,
    word2md_run_root: Path | None = None,
    reuse_raw_responses: bool = False,
    contract_filter: str | None = None,
) -> dict[str, str]:
    """Internal helper."""

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_source_path = output_dir / "dataset_from_word2md.json"
    build_dataset(
        PROJECT_ROOT,
        run_id,
        dataset_source_path,
        word2md_run_root=word2md_run_root,
    )
    dataset_payload = load_dataset_payload(dataset_source_path)
    dataset_payload = filter_contracts(dataset_payload, contract_filter=contract_filter)

    raw_dir = output_dir / "raw_responses"
    debug_dir = output_dir / "debug_requests"
    raw_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    local_prediction_dump: list[dict[str, Any]] = []
    for contract in dataset_payload.get("contracts", []):
        if not isinstance(contract, dict):
            continue
        contract_id = str(contract.get("contract_id", "")).strip()
        contract_text = str(contract.get("full_contract_text", "")).strip()
        if not contract_id or not contract_text:
            contract.setdefault("participants", {})["local_llm"] = []
            continue

        raw_path = raw_dir / f"{contract_id}.txt"
        if reuse_raw_responses and raw_path.exists():
            raw_text = raw_path.read_text(encoding="utf-8")
        else:
            prompt = USER_PROMPT_TEMPLATE.format(contract_text=contract_text)
            raw_text = send_chat(
                runtime,
                [
                    ("system", SYSTEM_PROMPT),
                    ("user", prompt),
                ],
                debug_path=debug_dir / f"{contract_id}.request.json",
            )
            raw_path.write_text(raw_text, encoding="utf-8")

        risks = parse_local_risks(contract_id, raw_text)
        contract.setdefault("participants", {})["local_llm"] = [asdict(item) for item in risks]
        local_prediction_dump.append(
            {
                "contract_id": contract_id,
                "risk_count": len(risks),
                "risks": [asdict(item) for item in risks],
            }
        )

    prediction_path = output_dir / "local_llm_predictions.json"
    prediction_path.write_text(json.dumps(local_prediction_dump, ensure_ascii=False, indent=2), encoding="utf-8")

    derived_dataset_path = output_dir / "dataset_with_local_llm.json"
    derived_dataset_path.write_text(json.dumps(dataset_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output_dir": str(output_dir),
        "dataset_source_path": str(dataset_source_path),
        "dataset_path": str(derived_dataset_path),
        "prediction_path": str(prediction_path),
    }

