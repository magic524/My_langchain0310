"""最简单的本地 LLM 对话脚本（OpenAI 兼容 vLLM）

使用方法：设置环境变量 `LOCAL_LLM_API_URL`（默认为 http://10.130.61.231:8001/v1）
和可选的 `LOCAL_LLM_API_KEY`，然后运行脚本：

    python examples/local_LLM/chat_local_llm.py

按 Ctrl+D 或输入 EOF 结束对话。
"""
from __future__ import annotations

import os
import requests
from typing import Any, Dict


API_URL = os.environ.get("LOCAL_LLM_API_URL", "http://10.130.61.231:8001/v1")
API_KEY = os.environ.get("LOCAL_LLM_API_KEY", "")
DEFAULT_MODEL = os.environ.get("LOCAL_LLM_MODEL", "InstructModel")


def chat_once(prompt: str, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """向本地 vLLM (OpenAI 兼容) 发送一次对话请求并返回解析后的结果。"""
    url = API_URL.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def extract_text(resp: Dict[str, Any]) -> str:
    """从常见的 OpenAI 兼容响应中提取文本内容。"""
    try:
        choice = resp.get("choices", [])[0]
        # GPT-style: choice.message.content
        if isinstance(choice, dict):
            msg = choice.get("message") or {}
            if isinstance(msg, dict) and msg.get("content"):
                return msg.get("content")
            if choice.get("text"):
                return choice.get("text")
        return str(resp)
    except Exception:
        return str(resp)


def main() -> None:
    print("本地 LLM 接口:", API_URL)
    print("模型:", DEFAULT_MODEL)
    print("输入你的问题，回车发送。按 Ctrl+D 退出。\n")

    try:
        while True:
            try:
                prompt = input("You: ")
            except EOFError:
                print("\n退出。")
                break
            if not prompt.strip():
                continue
            try:
                resp = chat_once(prompt)
                text = extract_text(resp)
            except Exception as e:
                text = f"请求失败: {e}"
            print("LLM:", text)
    except KeyboardInterrupt:
        print("\n已中断，退出。")


if __name__ == "__main__":
    main()
