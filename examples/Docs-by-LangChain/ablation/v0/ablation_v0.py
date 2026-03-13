#!/usr/bin/env python3
"""Ablation v0: prompt-only contract review for a single doc/docx.

用法示例：
    python ablation_v0.py --input-file <path/to/file.docx> --output out.md

说明：脚本会尝试导入同目录上级的 `contract_review_agent.py` 中的解析函数，
并采用 OpenAI 兼容的 HTTP 接口（`OPENAI_API_BASE` + `/chat/completions`）发送 system+human 消息。
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import json
from pathlib import Path
from typing import Any

import requests
import re


def load_contract_module() -> Any:
    # contract_review_agent.py 在 examples/Docs-by-LangChain
    base = Path(__file__).resolve().parents[2]
    module_path = base / "contract_review_agent.py"
    spec = importlib.util.spec_from_file_location("contract_review_agent", str(module_path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register module in sys.modules before executing to ensure dataclass
    # and other decorators that inspect sys.modules work correctly.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def send_chat_http(config: Any, messages: list[tuple[str, str]]) -> dict:
    if not config.base_url:
        raise RuntimeError("OPENAI_API_BASE (model endpoint) is required for this script")
    url = config.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key and config.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload: dict[str, Any] = {
        "model": config.model_name,
        "messages": [{"role": r, "content": c} for r, c in messages],
        "temperature": float(config.temperature),
    }
    if getattr(config, "extra_body", None):
        payload.update(config.extra_body)

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def build_markdown_report(target_path: Path, paragraphs: list[str], reviews: list[str]) -> str:
    lines = ["# Ablation v0 — Prompt-only 审查报告", "", f"- 待审文件：{target_path}", "", "## 审查结果", ""]
    if not paragraphs:
        lines.append("无可审查段落。")
        return "\n".join(lines)

    for i, (p, r) in enumerate(zip(paragraphs, reviews), start=1):
        lines.extend([f"### 条款 {i}", "", "**原文：**", "", p, "", "**审查：**", "", r, ""])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablation v0: prompt-only contract review")
    parser.add_argument("--input-file", required=True, help="doc/docx 待审文件")
    parser.add_argument("--output", help="输出 Markdown 文件路径", default=None)
    parser.add_argument("--max-paragraphs", type=int, default=10)
    parser.add_argument("--min-chars", type=int, default=30)
    args = parser.parse_args()

    module = load_contract_module()
    config = module.configure_runtime_env()

    input_path = Path(args.input_file)
    try:
        parsed = module.parse_word_file(input_path, role="original")
    except module.DocExtractionUnavailableError:
        parsed = module.extract_doc_best_effort(input_path, role="original")

    paragraphs = module.select_target_paragraphs(parsed, max_paragraphs=args.max_paragraphs, min_chars=args.min_chars)

    reviews: list[str] = []
    for paragraph in paragraphs:
        human_prompt = (
            "请仅参考下列目标条款，用审查助手的口吻给出批注式审查结果。输出要遵循：\n\n"
            "主要语言使用：中文\n"
            "风险级别：高 / 中 / 低\n问题说明：1-3 句\n审查批注：可直接给业务或法务\n建议修改：必要时给替换文本\n参考依据：如果无法判断则写 '参考不足'\n\n"
            f"目标条款：\n{paragraph}\n"
        )

        messages = [("system", module.SYSTEM_PROMPT), ("user", human_prompt)]
        try:
            resp = send_chat_http(config, messages)
            # 尝试兼容多种响应结构
            choice = resp.get("choices", [])[0]
            text = ""
            if isinstance(choice, dict):
                msg = choice.get("message") or {}
                if isinstance(msg, dict) and msg.get("content"):
                    text = msg.get("content")
                elif choice.get("text"):
                    text = choice.get("text")
            if not text:
                text = json.dumps(resp, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - surface errors to the user
            text = f"请求失败：{exc}"

        # 清洗模型输出：剥掉思维链、英文分析块与 <think> 标签等，只保留中文结果段落
        def clean_model_output(s: str) -> str:
            if not s:
                return s
            # 删除 <think> ... </think> 区块（跨行）
            s = re.sub(r"(?is)<think>.*?</think>", "", s)
            # 删除以 Thinking Process 或 Thinking 开头的英文分析块（直到遇到中文行或结构化标签）
            parts = s.splitlines()
            cleaned_lines: list[str] = []
            skip_english_block = False
            for line in parts:
                stripped = line.strip()
                # 跳过注释样式的占位符（如 /* Lines ... omitted */）
                if stripped.startswith("/*") and stripped.endswith("*/"):
                    continue
                # 若行包含明显中文字符，则保留并结束任何跳过状态
                if re.search(r"[\u4e00-\u9fff]", stripped):
                    cleaned_lines.append(line)
                    skip_english_block = False
                    continue
                # 保留常见 Markdown 标题/结构行（例如 ###、-、**）
                if re.match(r"^#{1,6}\s+", stripped) or stripped.startswith("**") or stripped.startswith("-"):
                    cleaned_lines.append(line)
                    continue
                # 如果当前行以 Thinking Process 开头，进入跳过模式
                if re.match(r"(?i)^\s*Thinking Process[:\s]*", stripped):
                    skip_english_block = True
                    continue
                # 如果处于跳过模式且该行主要为英文/数字/标点，则继续跳过
                if skip_english_block:
                    # 如果偶然出现英文小标题也跳过
                    if re.search(r"[A-Za-z]", stripped) and not re.search(r"[\u4e00-\u9fff]", stripped):
                        continue
                    else:
                        skip_english_block = False
                # 非中文行且非结构化行，默认忽略（以去除英文思路输出）
                # 但保留简短的字段标签（如 '风险级别：' 等），这些包含中文即可被上面保留
            # 合并并压缩多空行
            result = "\n".join(cleaned_lines)
            result = re.sub(r"\n{3,}", "\n\n", result)
            result = result.strip()
            return result or s

        text = clean_model_output(text)

        reviews.append(text)

    out_md = build_markdown_report(input_path, paragraphs, reviews)
    out_path = Path(args.output) if args.output else input_path.with_suffix(input_path.suffix + ".ablation.v0.md")
    out_path.write_text(out_md, encoding="utf-8")
    print(f"输出已写入：{out_path}")


if __name__ == "__main__":
    main()
