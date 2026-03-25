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


SYSTEM_PROMPT = """浣犳槸鍚堝悓瀹℃煡鍔╂墜銆?
浣犱細鏀跺埌涓€鏁翠唤鍚堝悓鐨?markdown 鍏ㄦ枃銆?浣犵殑浠诲姟鏄壘鍑哄悎鍚屼腑鐨勯闄╃偣锛屽苟杈撳嚭涓ユ牸 JSON銆?
瑕佹眰锛?1. 鍙緭鍑?JSON锛屼笉瑕佽緭鍑鸿В閲婃€у墠鍚庣紑銆?2. 椋庨櫓鐐硅灏介噺缁戝畾鍘熷悎鍚屼腑鐨勫叿浣撴潯娆惧師鏂囥€?3. explanation 瑕佽鏄庨闄╁師鍥犳垨涓嶅埄鍚庢灉銆?4. suggestion 瑕佺粰鍑哄彲鎵ц鐨勪慨鏀瑰缓璁€?5. 濡傛灉娌℃湁璇嗗埆鍒伴闄╋紝杈撳嚭 {"risks": []}銆?"""


USER_PROMPT_TEMPLATE = """璇峰鏌ヤ笅闈㈣繖浠藉悎鍚屽叏鏂囷紝骞舵壘鍑洪闄╃偣銆?
杈撳嚭鏍煎紡蹇呴』鏄細
{{
  "risks": [
    {{
      "title": "椋庨櫓鏍囬",
      "clause_text": "瀵瑰簲鐨勫悎鍚屽師鏂囩墖娈?,
      "explanation": "椋庨櫓鍘熷洜鎴栧悗鏋?,
      "suggestion": "淇敼寤鸿"
    }}
  ]
}}

娉ㄦ剰锛?- 杩欐槸鏁翠唤鍚堝悓鍏ㄦ枃杈撳叆锛屼笉瑕佹寜娈佃惤閫愭鍥炵瓟銆?- `title` 瑕佺畝娲佹槑纭€?- `clause_text` 灏介噺鎽樺綍鍘熷悎鍚屼腑鐨勫叧閿潯娆惧師鏂囥€?- `suggestion` 涓嶈鍙啓鈥滃缓璁畬鍠勨€濓紝瑕佸敖閲忓啓鍏蜂綋銆?
鍚堝悓鍏ㄦ枃濡備笅锛?
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
        primary_error = f"ChatOpenAI 璋冪敤澶辫触: {exc}"

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
            fallback_error = f"ChatOpenAI 闄嶇骇璋冪敤澶辫触: {fallback_exc}"

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
        msg = f"鏈壘鍒板尮閰嶅悎鍚? {contract_filter}"
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

