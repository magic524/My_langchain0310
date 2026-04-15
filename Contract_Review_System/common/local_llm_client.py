from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# 这一组路径常量用于定位当前公共模块所在位置，以及共享配置文件 `.env` 的默认位置。
CURRENT_FILE = Path(__file__).resolve()
COMMON_ROOT = CURRENT_FILE.parent
CONTRACT_REVIEW_ROOT = CURRENT_FILE.parents[1]
DEFAULT_ENV_PATH = CONTRACT_REVIEW_ROOT / ".env"


# 这个数据类负责统一保存本地模型运行时所需的配置。
# 其它调用层也可以直接复用这份结构。
@dataclass(slots=True)
class RuntimeConfig:
    """Shared runtime config for the local LLM client."""

    model_name: str
    api_key: str
    base_url: str
    temperature: float
    extra_body: dict[str, Any] | None
    request_timeout_seconds: float


# 这个函数负责手动解析 `.env` 文件，避免额外引入 `python-dotenv` 依赖。
# 当前只支持最常见的 `KEY=VALUE` 形式，已经够你这个项目使用。
def load_env_file(env_path: Path) -> dict[str, str]:
    """Load key-value pairs from a `.env` file."""

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


# 这个函数负责决定“当前应该读哪个 `.env`”。
# 默认读取 `Contract_Review_System/.env`，也支持你后续显式传入别的配置文件路径做测试。
def resolve_runtime_env_path(explicit_env_path: Path | None = None) -> Path:
    """Resolve the shared runtime `.env` path."""

    if explicit_env_path is not None:
        resolved = explicit_env_path.resolve()
        if not resolved.exists():
            msg = f"指定的 .env 不存在: {resolved}"
            raise FileNotFoundError(msg)
        return resolved

    resolved = DEFAULT_ENV_PATH.resolve()
    if not resolved.exists():
        msg = f"共享 .env 不存在: {resolved}"
        raise FileNotFoundError(msg)
    return resolved


# 这个函数负责把 `.env` 里的字符串配置，整理成结构化的 `RuntimeConfig`。
# 这里统一兼容了几个常见字段名，方便你以后迁移或兼容旧配置。
def load_runtime_config(env_path: Path | None = None) -> RuntimeConfig:
    """Load local LLM runtime config from the shared `.env`."""

    values = load_env_file(resolve_runtime_env_path(env_path))
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

    request_timeout_raw = values.get("OPENAI_REQUEST_TIMEOUT", "600").strip()
    try:
        request_timeout_seconds = float(request_timeout_raw)
    except ValueError:
        request_timeout_seconds = 600.0

    return RuntimeConfig(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        extra_body=extra_body,
        request_timeout_seconds=max(request_timeout_seconds, 60.0),
    )


# 这个函数负责把消息列表组装成 OpenAI 兼容接口需要的请求体。
# 如果 `.env` 中配置了额外参数，也会在这里一起带上。
def build_payload(
    runtime: RuntimeConfig,
    messages: list[tuple[str, str]],
    *,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an OpenAI-compatible chat payload."""

    payload: dict[str, Any] = {
        "model": runtime.model_name,
        "messages": [{"role": role, "content": content} for role, content in messages],
        "temperature": runtime.temperature,
    }
    merged_extra_body = extra_body if extra_body is not None else runtime.extra_body
    if merged_extra_body:
        payload.update(merged_extra_body)
    return payload


# 这个函数负责真正发 HTTP 请求到公司的本地模型 OpenAI 兼容接口。
# 它只做一件事：发送请求并尽量把错误信息整理得清楚一些。
def post_chat_request(runtime: RuntimeConfig, payload: dict[str, Any]) -> str:
    """Send a request to the local OpenAI-compatible chat endpoint."""

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
        with urllib.request.urlopen(request, timeout=runtime.request_timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        msg = f"模型接口请求失败: HTTP {exc.code} {detail}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:
        msg = (
            f"模型接口连接失败: {exc.reason}. "
            f"request_timeout_seconds={runtime.request_timeout_seconds}"
        )
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


# 这是对外最直接的调用函数。
# 业务项目通常只需要：加载配置 -> 组织 messages -> 调 `send_chat()`。
def send_chat(
    runtime: RuntimeConfig,
    messages: list[tuple[str, str]],
    *,
    extra_body: dict[str, Any] | None = None,
) -> str:
    """Call the shared local LLM API."""

    payload = build_payload(runtime, messages, extra_body=extra_body)
    return post_chat_request(runtime, payload)
