from __future__ import annotations

import argparse
import json
import os
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import find_dotenv, load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
REPORTS_DIR = SCRIPT_DIR / "reports"


@dataclass(slots=True)
class RuntimeConfig:
    """Runtime model configuration for OpenAI-compatible chat APIs."""

    model_name: str
    model_provider: str
    temperature: float
    api_key: str
    base_url: str
    extra_body: dict[str, Any] | None


@dataclass(slots=True)
class TestCheck:
    """Single validation check for model test outputs."""

    name: str
    passed: bool
    detail: str


def _parse_json_env(env_name: str) -> dict[str, Any] | None:
    """Parse a JSON object from environment variables.

    Args:
        env_name: Environment variable name.

    Returns:
        Parsed dict object, or None if env not set.

    Raises:
        ValueError: If value exists but is not valid JSON object.
    """
    raw_value = os.getenv(env_name)
    if not raw_value:
        return None

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        msg = f"环境变量 {env_name} 不是合法 JSON：{exc}"
        raise ValueError(msg) from exc

    if not isinstance(parsed, dict):
        msg = f"环境变量 {env_name} 必须是 JSON 对象。"
        raise ValueError(msg)
    return parsed


def load_runtime_config() -> RuntimeConfig:
    """Load model settings from `.env` in current workspace.

    Returns:
        RuntimeConfig for OpenAI-compatible endpoint.

    Raises:
        RuntimeError: If required fields are missing.
    """
    load_dotenv(find_dotenv(usecwd=True))

    model_name = (
        os.getenv("OPENAI_LLM_MODEL")
        or os.getenv("OPENAI_MODEL_NAME")
        or os.getenv("OPENAI_MODEL")
        or "qwen-plus"
    )
    model_provider = os.getenv("OPENAI_MODEL_PROVIDER", "openai")
    openai_api_base = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    temperature_raw = os.getenv("OPENAI_TEMPERATURE", "0.0")
    extra_body = _parse_json_env("OPENAI_EXTRA_BODY")

    if dashscope_api_key and not openai_api_key:
        openai_api_key = dashscope_api_key

    if openai_api_base and not openai_api_key:
        openai_api_key = "EMPTY"

    if not openai_api_base:
        msg = (
            "未检测到 OPENAI_API_BASE / OPENAI_BASE_URL。"
            "请在 datatype_test/.env 中配置 OpenAI 兼容接口地址。"
        )
        raise RuntimeError(msg)

    try:
        temperature = float(temperature_raw)
    except ValueError as exc:
        msg = f"OPENAI_TEMPERATURE 不是合法数字：{temperature_raw}"
        raise RuntimeError(msg) from exc

    return RuntimeConfig(
        model_name=model_name,
        model_provider=model_provider,
        temperature=temperature,
        api_key=openai_api_key or "EMPTY",
        base_url=openai_api_base,
        extra_body=extra_body,
    )


def _send_chat_http(config: RuntimeConfig, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Send one chat completion request via OpenAI-compatible HTTP API."""
    url = config.base_url.rstrip("/") + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.api_key and config.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload: dict[str, Any] = {
        "model": config.model_name,
        "messages": messages,
        "temperature": config.temperature,
    }
    if config.extra_body:
        payload.update(config.extra_body)

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def _extract_response_text(response: dict[str, Any]) -> str:
    """Extract assistant text from chat completion response."""
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


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _extract_json_block(raw_text: str) -> dict[str, Any]:
    """Extract JSON object from a model response text.

    The response can be plain JSON or fenced with ```json.
    """
    text = raw_text.strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    if text.startswith("{") and text.endswith("}"):
        return _safe_json_loads(text)

    json_like = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if json_like:
        return _safe_json_loads(json_like.group(1))

    msg = "模型输出未找到合法 JSON 对象"
    raise ValueError(msg)


def _safe_json_loads(text: str) -> dict[str, Any]:
    """Parse JSON with a minimal repair pass for invalid backslash escapes."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        parsed = json.loads(repaired)
        if isinstance(parsed, dict):
            return parsed

    msg = "模型输出中的 JSON 不是对象类型"
    raise ValueError(msg)


def _first_n_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[...内容因长度限制已截断...]"


def resolve_md_path(*, md_path: str | None, run_id: str | None, sample_id: str | None) -> Path:
    """Resolve markdown input path from explicit path or run/sample pair."""
    if md_path:
        path = Path(md_path).expanduser().resolve()
        if not path.exists():
            msg = f"指定 Markdown 文件不存在：{path}"
            raise FileNotFoundError(msg)
        return path

    if not run_id or not sample_id:
        msg = "未提供 --md-path 时，必须同时提供 --run-id 和 --sample-id"
        raise ValueError(msg)

    path = (OUTPUTS_DIR / run_id / sample_id / "output.md").resolve()
    if not path.exists():
        msg = f"未找到转换后的 Markdown：{path}"
        raise FileNotFoundError(msg)
    return path


def build_turn1_prompt(md_text: str) -> str:
    """Build first-turn structured extraction prompt."""
    return textwrap.dedent(
        f"""
        你将读取一份由 Word 合同转换得到的 Markdown 文本。
        请判断你是否能正确识别其结构，并抽取关键信息。

        要求：
        1. 只基于给定 Markdown 内容回答，不要脑补未出现信息。
        2. 必须输出合法 JSON（不要输出 JSON 以外内容）。
        3. 字段必须完整，缺失信息请填 null。
        4. 所有 evidence 必须是原文中的直接片段（尽量逐字一致）。

        JSON schema：
        {{
          "doc_understanding": {{
            "contract_title": "string | null",
            "parties": ["string", "..."],
            "section_headings": ["string", "..."],
            "numbering_style_detected": "string | null",
            "table_detected": true
          }},
          "risk_signals": [
            {{"risk": "string", "evidence": "string", "reason": "string"}}
          ],
          "uncertainties": ["string", "..."]
        }}

        Markdown 合同文本如下：
        {md_text}
        """
    ).strip()


def build_turn2_prompt(turn1_json: dict[str, Any]) -> str:
    """Build second-turn follow-up prompt for consistency and citation checks."""
    compact = json.dumps(turn1_json, ensure_ascii=False, indent=2)
    return textwrap.dedent(
        f"""
        你上一轮给出的结构化结果如下：
        {compact}

        现在请做一次自检，输出 Markdown（不是 JSON），格式必须严格如下：
        - 识别结论：通过/不通过
        - 主要依据：
          1) ...
          2) ...
        - 高风险条款建议核验点：
          1) ...（引用或概述对应证据）
          2) ...
        - 置信度：0-100 的整数

        规则：
        1. 若证据不足，结论必须是“不通过”。
        2. 结论和依据必须与上一轮 JSON 一致。
        3. 使用中文回答。
        """
    ).strip()


def validate_turn1(turn1_json: dict[str, Any], md_text: str, turn1_raw: str) -> list[TestCheck]:
    """Validate first-turn JSON quality and grounding."""
    checks: list[TestCheck] = []

    thinking_leak = bool(re.search(r"Thinking Process|<think>|</think>", turn1_raw, flags=re.IGNORECASE))
    checks.append(
        TestCheck(
            name="无思维草稿泄漏",
            passed=not thinking_leak,
            detail="输出不应包含 Thinking Process / <think> 草稿内容",
        )
    )

    doc_understanding = turn1_json.get("doc_understanding")
    checks.append(
        TestCheck(
            name="doc_understanding 字段",
            passed=isinstance(doc_understanding, dict),
            detail="必须包含 doc_understanding 对象",
        )
    )

    parties = doc_understanding.get("parties") if isinstance(doc_understanding, dict) else None
    checks.append(
        TestCheck(
            name="parties 类型",
            passed=isinstance(parties, list),
            detail="parties 必须是列表",
        )
    )

    headings = doc_understanding.get("section_headings") if isinstance(doc_understanding, dict) else None
    checks.append(
        TestCheck(
            name="section_headings 类型",
            passed=isinstance(headings, list),
            detail="section_headings 必须是列表",
        )
    )

    risk_signals = turn1_json.get("risk_signals")
    checks.append(
        TestCheck(
            name="risk_signals 类型",
            passed=isinstance(risk_signals, list),
            detail="risk_signals 必须是列表",
        )
    )

    evidence_ok = True
    evidence_detail = "所有 evidence 至少可在原文找到部分匹配"
    normalized_md = _normalize_for_match(md_text)

    if isinstance(risk_signals, list):
        for idx, item in enumerate(risk_signals, start=1):
            if not isinstance(item, dict):
                evidence_ok = False
                evidence_detail = f"risk_signals[{idx}] 不是对象"
                break
            evidence = str(item.get("evidence", "")).strip()
            if not evidence:
                evidence_ok = False
                evidence_detail = f"risk_signals[{idx}] evidence 为空"
                break
            normalized_ev = _normalize_for_match(evidence)
            if len(normalized_ev) >= 8 and normalized_ev not in normalized_md:
                evidence_ok = False
                evidence_detail = f"risk_signals[{idx}] evidence 未在 Markdown 原文命中"
                break

    checks.append(
        TestCheck(
            name="evidence 引用可追溯",
            passed=evidence_ok,
            detail=evidence_detail,
        )
    )

    return checks


def validate_turn2(turn2_text: str) -> list[TestCheck]:
    """Validate second-turn report format."""
    required_tokens = ["识别结论：", "主要依据：", "高风险条款建议核验点：", "置信度："]
    checks: list[TestCheck] = []
    for token in required_tokens:
        checks.append(
            TestCheck(
                name=f"包含字段 {token}",
                passed=token in turn2_text,
                detail=f"应包含 {token}",
            )
        )

    confidence_match = re.search(r"置信度\s*[:：]\s*(\d{1,3})", turn2_text)
    confidence_ok = False
    confidence_detail = "未识别到 0-100 的整数置信度"
    if confidence_match:
        value = int(confidence_match.group(1))
        confidence_ok = 0 <= value <= 100
        confidence_detail = f"检测到置信度 {value}"

    checks.append(TestCheck(name="置信度范围", passed=confidence_ok, detail=confidence_detail))
    return checks


def _score(checks: list[TestCheck]) -> int:
    if not checks:
        return 0
    passed = sum(1 for item in checks if item.passed)
    return round(100 * passed / len(checks))


def build_report_markdown(
    *,
    run_id: str,
    sample_id: str,
    md_path: Path,
    model_name: str,
    turn1_raw: str,
    turn2_raw: str,
    turn1_checks: list[TestCheck],
    turn2_checks: list[TestCheck],
) -> str:
    """Build a readable markdown report for auditing."""
    turn1_score = _score(turn1_checks)
    turn2_score = _score(turn2_checks)
    overall = round((turn1_score + turn2_score) / 2)

    lines: list[str] = [
        "# AI 对话识别测试报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Run ID：{run_id}",
        f"- Sample ID：{sample_id}",
        f"- Markdown 输入：{md_path}",
        f"- 模型：{model_name}",
        "",
        "## 测试评分",
        "",
        f"- Turn 1（结构化抽取）评分：{turn1_score}",
        f"- Turn 2（自检对话）评分：{turn2_score}",
        f"- 综合评分：{overall}",
        "",
        "## Turn 1 检查项",
        "",
    ]

    for check in turn1_checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{status}] {check.name}：{check.detail}")

    lines += ["", "## Turn 2 检查项", ""]
    for check in turn2_checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{status}] {check.name}：{check.detail}")

    lines += [
        "",
        "## Turn 1 原始输出",
        "",
        "```text",
        turn1_raw.strip(),
        "```",
        "",
        "## Turn 2 原始输出",
        "",
        "```text",
        turn2_raw.strip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def run_interactive_chat(config: RuntimeConfig, md_text: str) -> None:
    """Run a manual multi-turn chat against converted markdown.

    This mode is convenient when you want quick exploratory questions.
    """
    system_prompt = (
        "你是一名合同审查助手。你将仅依据给定 Markdown 合同文本回答问题，"
        "禁止编造条款；若证据不足请明确说明“信息不足”。"
    )
    context_prompt = f"以下是合同 Markdown 文本，请记住它并用于后续问答：\n\n{md_text}"

    history: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_prompt},
    ]

    print("\n[交互模式] 输入 exit 退出。")
    while True:
        user_input = input("\n你：").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("已退出交互模式。")
            break

        history.append({"role": "user", "content": user_input})
        response = _send_chat_http(config, history)
        answer = _extract_response_text(response)
        history.append({"role": "assistant", "content": answer})
        print("\n模型：")
        print(answer)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "AI 对话测试脚本：验证模型能否正确识别 convert.py 导出的 Markdown 合同内容，"
            "并给出结构化抽取与可追溯证据。"
        )
    )
    parser.add_argument("--md-path", default=None, help="直接指定要测试的 Markdown 文件路径")
    parser.add_argument("--run-id", default=None, help="转换运行 ID（与 --sample-id 配合）")
    parser.add_argument("--sample-id", default=None, help="样本 ID（与 --run-id 配合）")
    parser.add_argument("--max-chars", type=int, default=20000, help="发送给模型的最大字符数，默认 20000")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="开启手动多轮对话模式（不做自动评分）",
    )
    args = parser.parse_args()

    config = load_runtime_config()
    md_path = resolve_md_path(md_path=args.md_path, run_id=args.run_id, sample_id=args.sample_id)
    md_text = md_path.read_text(encoding="utf-8")
    prompt_md = _first_n_chars(md_text, args.max_chars)

    if args.interactive:
        run_interactive_chat(config, prompt_md)
        return

    run_id = args.run_id or f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    sample_id = args.sample_id or md_path.parent.name

    system_prompt = (
        "你是合同审查前置识别助手。任务是验证模型对 Markdown 合同结构的识别能力。"
        "只可依据用户提供文本，不可编造。"
    )

    turn1_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_turn1_prompt(prompt_md)},
    ]
    turn1_response = _send_chat_http(config, turn1_messages)
    turn1_raw = _extract_response_text(turn1_response)
    turn1_json = _extract_json_block(turn1_raw)

    turn2_messages = turn1_messages + [
        {"role": "assistant", "content": turn1_raw},
        {"role": "user", "content": build_turn2_prompt(turn1_json)},
    ]
    turn2_response = _send_chat_http(config, turn2_messages)
    turn2_raw = _extract_response_text(turn2_response)

    turn1_checks = validate_turn1(turn1_json, prompt_md, turn1_raw)
    turn2_checks = validate_turn2(turn2_raw)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"{stamp}_chat_test_{sample_id}.md"
    report_text = build_report_markdown(
        run_id=run_id,
        sample_id=sample_id,
        md_path=md_path,
        model_name=config.model_name,
        turn1_raw=turn1_raw,
        turn2_raw=turn2_raw,
        turn1_checks=turn1_checks,
        turn2_checks=turn2_checks,
    )
    report_path.write_text(report_text, encoding="utf-8")

    json_out = REPORTS_DIR / f"{stamp}_chat_test_{sample_id}.json"
    json_out.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "sample_id": sample_id,
                "md_path": str(md_path),
                "model_name": config.model_name,
                "turn1_raw": turn1_raw,
                "turn1_json": turn1_json,
                "turn2_raw": turn2_raw,
                "turn1_checks": [
                    {"name": check.name, "passed": check.passed, "detail": check.detail}
                    for check in turn1_checks
                ],
                "turn2_checks": [
                    {"name": check.name, "passed": check.passed, "detail": check.detail}
                    for check in turn2_checks
                ],
                "turn1_score": _score(turn1_checks),
                "turn2_score": _score(turn2_checks),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n================ AI 对话测试完成 ================")
    print(f"模型           : {config.model_name} ({config.model_provider})")
    print(f"Markdown 输入  : {md_path}")
    print(f"报告文件       : {report_path}")
    print(f"结果 JSON      : {json_out}")
    print(f"Turn1 分数     : {_score(turn1_checks)}")
    print(f"Turn2 分数     : {_score(turn2_checks)}")
    print("================================================\n")


if __name__ == "__main__":
    main()
