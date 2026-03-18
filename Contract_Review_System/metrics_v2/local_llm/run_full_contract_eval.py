from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
METRICS_V2_ROOT = CURRENT_FILE.parents[1]
SRC_ROOT = METRICS_V2_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.dataset_builder import build_dataset
from contract_metrics_v2.evaluator import evaluate_dataset
from contract_metrics_v2.reporter import write_reports
from contract_metrics_v2.types import RiskItem


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


@dataclass(slots=True)
class RuntimeConfig:
    """本地模型运行配置。"""

    model_name: str
    api_key: str
    base_url: str
    temperature: float
    extra_body: dict[str, Any] | None


def load_env_file(env_path: Path) -> dict[str, str]:
    """手动读取 .env，避免额外依赖。"""

    values: dict[str, str] = {}
    if not env_path.exists():
        msg = f".env 不存在: {env_path}"
        raise FileNotFoundError(msg)

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_runtime_config(env_path: Path) -> RuntimeConfig:
    """从 metrics_v2/.env 读取本地模型配置。"""

    values = load_env_file(env_path)
    model_name = (
        values.get("OPENAI_LLM_MODEL")
        or values.get("OPENAI_MODEL_NAME")
        or values.get("OPENAI_MODEL")
        or "InstructModel"
    )
    base_url = values.get("OPENAI_API_BASE") or values.get("OPENAI_BASE_URL")
    if not base_url:
        msg = "缺少 OPENAI_API_BASE / OPENAI_BASE_URL"
        raise RuntimeError(msg)

    api_key = values.get("OPENAI_API_KEY", "EMPTY")
    temperature_raw = values.get("OPENAI_TEMPERATURE", "0.0")
    try:
        temperature = float(temperature_raw)
    except ValueError:
        temperature = 0.0

    extra_body: dict[str, Any] | None = None
    extra_body_raw = values.get("OPENAI_EXTRA_BODY", "").strip()
    if extra_body_raw:
        loaded = json.loads(extra_body_raw)
        if isinstance(loaded, dict):
            extra_body = loaded

    return RuntimeConfig(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        extra_body=extra_body,
    )


def build_payload(
    runtime: RuntimeConfig,
    messages: list[tuple[str, str]],
    *,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    """构造发送给本地模型的请求体。"""

    payload: dict[str, Any] = {
        "model": runtime.model_name,
        "messages": [{"role": role, "content": content} for role, content in messages],
        "temperature": runtime.temperature,
    }
    if extra_body:
        payload.update(extra_body)
    return payload


def post_chat_request(runtime: RuntimeConfig, payload: dict[str, Any]) -> str:
    """向 OpenAI 兼容接口发送一次请求。"""

    url = runtime.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if runtime.api_key and runtime.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {runtime.api_key}"

    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        msg = f"模型接口请求失败: HTTP {exc.code} {detail}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:
        msg = f"模型接口连接失败: {exc.reason}"
        raise RuntimeError(msg) from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        msg = f"模型接口返回的内容不是合法 JSON: {body[:400]}"
        raise RuntimeError(msg) from exc
    choices = parsed.get("choices") or []
    if not choices:
        return body
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    return body


def send_chat_via_langchain(runtime: RuntimeConfig, messages: list[tuple[str, str]]) -> str:
    """优先按公司文档推荐的 ChatOpenAI 方式调用本地模型。"""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = (
            "当前环境缺少 `langchain_openai` 或 `langchain_core`，"
            "请先在 `langchain` conda 环境中运行，或安装相应依赖。"
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
    """生成适合落盘的调试请求体，避免把整份合同重复写入调试文件。"""

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
        preview = content[:800]
        message["content_preview"] = preview
        message["content_length"] = len(content)
        message.pop("content", None)
    return sanitized


def write_debug_payload(debug_path: Path, payload: dict[str, Any], *, note: str) -> None:
    """写入当前请求的调试信息，便于排查服务端 500。"""

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
    """调用本地模型，并在 500 时自动降级重试。"""

    primary_payload = build_payload(runtime, messages, extra_body=runtime.extra_body)
    if debug_path is not None:
        write_debug_payload(debug_path, primary_payload, note="primary_request")

    try:
        return send_chat_via_langchain(runtime, messages)
    except RuntimeError as exc:
        primary_error = str(exc)
    except Exception as exc:
        primary_error = f"ChatOpenAI 调用失败: {exc}"

    # 某些本地服务对 `OPENAI_EXTRA_BODY` 中的自定义参数兼容性较差，
    # 遇到 500 时退回最朴素的 OpenAI 兼容请求再试一次。
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
        except Exception as fallback_exc:
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
                "模型接口多次请求都失败。"
                f"首次调用: {primary_error}。"
                f"去掉 OPENAI_EXTRA_BODY 后的 ChatOpenAI 调用: {fallback_error}。"
                f"最终直接 HTTP 降级调用仍失败: {raw_fallback_error}"
            )
            raise RuntimeError(msg) from raw_fallback_exc

    raise RuntimeError(primary_error)


def extract_json_block(text: str) -> dict[str, Any]:
    """从模型输出中提取最后一个合法 JSON 对象。

    本地模型经常会先输出 `Thinking Process` 或示例 JSON，再在末尾给出最终答案。
    这里从后往前扫描 `{`，优先提取最后一个可被解析、且包含 `risks` 字段的对象。
    """

    stripped = text.strip()
    if not stripped:
        return {"risks": []}

    if "</think>" in stripped:
        stripped = stripped.split("</think>")[-1].strip()

    decoder = json.JSONDecoder()
    brace_indexes = [index for index, char in enumerate(stripped) if char == "{"]  # noqa: C416
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
    """当整段 JSON 非法时，按字段行兜底提取风险点。

    本地模型常见问题：
    1. 在正式 JSON 前输出长段推理
    2. 某个 value 内出现未转义引号，导致整体 JSON 失效

    只要最终答案仍保持一行一个字段的结构，这里就尽量把 `title /
    clause_text / explanation / suggestion` 救回来。
    """

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

        if line in {'{', '},'}:
            if current:
                results.append(current)
                current = {}
            continue

        if line == "}":
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

            # 用“首引号 + 行尾最后一个引号”兜底，允许 value 内部再出现未转义引号。
            end_quote_index = value_part.rfind('"')
            if end_quote_index <= 0:
                current[field] = value_part[1:].rstrip(",").strip()
                break

            value = value_part[1:end_quote_index]
            current[field] = value
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
    """把模型 JSON 结果转成 RiskItem。"""

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


def ensure_dataset(run_id: str) -> Path:
    """重建 metrics_v2 数据集，确保解析修复能生效。"""

    dataset_path = (
        PROJECT_ROOT
        / "Contract_Review_System"
        / "metrics_v2"
        / "outputs"
        / "datasets"
        / f"dataset_{run_id}.json"
    ).resolve()
    build_dataset(PROJECT_ROOT, run_id, dataset_path)
    return dataset_path


def load_dataset_payload(dataset_path: Path) -> dict[str, Any]:
    """读取原始数据集 JSON。"""

    return json.loads(dataset_path.read_text(encoding="utf-8"))


def filter_contracts(
    dataset_payload: dict[str, Any],
    *,
    contract_filter: str | None,
) -> dict[str, Any]:
    """按合同名称子串过滤数据集。"""

    if not contract_filter:
        return dataset_payload

    contracts = dataset_payload.get("contracts", [])
    if not isinstance(contracts, list):
        msg = "数据集 contracts 字段格式不正确"
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
    reuse_raw_responses: bool = False,
    contract_filter: str | None = None,
) -> dict[str, Any]:
    """执行本地模型预测并生成带 local_llm 的数据集。"""

    dataset_path = ensure_dataset(run_id)
    dataset_payload = load_dataset_payload(dataset_path)
    dataset_payload = filter_contracts(dataset_payload, contract_filter=contract_filter)

    output_dir = (METRICS_V2_ROOT / "local_llm" / "outputs" / run_id).resolve()
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
        "dataset_path": str(derived_dataset_path),
        "prediction_path": str(prediction_path),
    }


def main() -> None:
    """全文合同 + 本地模型 + metrics_v2 评估入口。"""

    parser = argparse.ArgumentParser(description="Run local LLM full-contract evaluation with metrics_v2")
    parser.add_argument("--run-id", required=True, help="word2md run id")
    parser.add_argument(
        "--participants",
        default="third_party,final_applied,local_llm",
        help="Participants to include in final report",
    )
    parser.add_argument(
        "--reuse-raw-responses",
        action="store_true",
        help="Reuse existing raw_responses/*.txt and only rerun parsing/evaluation",
    )
    parser.add_argument(
        "--contract-filter",
        default="",
        help="Only evaluate contracts whose contract_id contains this text",
    )
    args = parser.parse_args()

    env_path = (METRICS_V2_ROOT / ".env").resolve()
    runtime = load_runtime_config(env_path)
    pipeline_info = run_local_prediction(
        args.run_id,
        runtime,
        reuse_raw_responses=args.reuse_raw_responses,
        contract_filter=args.contract_filter.strip() or None,
    )

    participants = [item.strip() for item in args.participants.split(",") if item.strip()]
    payload = evaluate_dataset(Path(pipeline_info["dataset_path"]), participants=participants)
    report_files = write_reports(Path(pipeline_info["output_dir"]), payload)

    print(f"derived dataset: {pipeline_info['dataset_path']}")
    print(f"local predictions: {pipeline_info['prediction_path']}")
    print(f"evaluation report: {report_files['markdown']}")
    print(f"evaluation json: {report_files['json']}")


if __name__ == "__main__":
    main()
