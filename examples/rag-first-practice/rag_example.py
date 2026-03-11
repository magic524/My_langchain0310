#!/usr/bin/env python3
"""简易 RAG 演示脚本（兼容 LangChain 1.x）

说明：
- 若设置了环境变量 `OPENAI_API_KEY`，脚本会调用 OpenAI 兼容接口生成最终回答。
- 否则脚本只展示检索到的相关文档片段，便于理解检索部分行为。
"""
import os
import sys

from openai import OpenAI

def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)

# 如果你在本仓库根目录运行脚本，Python 可能会优先导入本地的 `langchain` 源码，
# 导致已用 `pip` 安装的 `langchain` 无法被使用。移除仓库根路径可以优先使用已安装的包。
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root in sys.path:
    try:
        sys.path.remove(repo_root)
    except ValueError:
        pass

try:
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS
except Exception as e:
    import traceback
    import importlib.util

    print("导入 langchain 相关模块失败，开始打印诊断信息：", file=sys.stderr)
    traceback.print_exc()
    print("\n-- sys.path 开始 --", file=sys.stderr)
    for p in sys.path:
        print(p, file=sys.stderr)
    print("-- sys.path 结束 --\n", file=sys.stderr)

    try:
        spec = importlib.util.find_spec("langchain")
        print("langchain spec:", spec, file=sys.stderr)
        if spec is not None:
            print("langchain origin:", getattr(spec, "origin", None), file=sys.stderr)
    except Exception:
        print("查找 langchain spec 时发生错误", file=sys.stderr)

    print("Python 可执行文件:", sys.executable, file=sys.stderr)
    fail(
        "请先安装依赖或检查本地源码是否遮蔽已安装包："
        "pip install -r requirements.txt（在 examples/rag-first-practice 下）"
    )


def build_vectorstore(texts: list[str]):
    """用 sentence-transformers 嵌入 + FAISS 构建向量库"""
    print("正在创建嵌入模型（sentence-transformers/all-MiniLM-L6-v2）...")
    embed = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    print("正在基于文本构建 FAISS 向量索引...")
    vs = FAISS.from_texts(texts, embed)
    return vs


def _build_openai_client() -> OpenAI:
    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        fail("未设置 OPENAI_API_KEY")

    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _answer_with_openai(question: str, contexts: list[str]) -> str:
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = _build_openai_client()
    context_block = "\n\n".join(f"[{idx + 1}] {text}" for idx, text in enumerate(contexts))
    system_prompt = (
        "你是一个问答助手。你必须优先依据提供的上下文回答，"
        "若上下文不足请明确说明不确定。"
    )
    user_prompt = (
        "以下是检索到的上下文：\n"
        f"{context_block}\n\n"
        f"用户问题：{question}\n"
        "请用中文简洁作答。"
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = resp.choices[0].message.content
    return content or ""


def interactive_with_openai(retriever) -> None:
    print("已检测到 OPENAI_API_KEY，进入 RAG 问答模式（输入 q 退出）。")
    print("可选环境变量：OPENAI_BASE_URL、OPENAI_MODEL")
    while True:
        q = input("问题(q退出): ")
        if q.strip().lower() in ("q", "quit", "exit"):
            break

        docs = retriever.invoke(q)
        contexts = [d.page_content for d in docs]
        if not contexts:
            print("未检索到相关文档。")
            continue

        out = _answer_with_openai(q, contexts)
        print("---- 回答 ----")
        print(out)
        print()


def _build_minimax_client() -> OpenAI:
    """构建用于调用阿里云百炼 DashScope OpenAI 兼容接口的客户端。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        fail("未设置 DASHSCOPE_API_KEY（MiniMax API Key）")
    base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def _answer_with_minimax(question: str, contexts: list[str]) -> str:
    """使用 MiniMax 接口基于检索到的上下文生成答案。"""
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    client = _build_minimax_client()
    context_block = "\n\n".join(f"[{idx + 1}] {text}" for idx, text in enumerate(contexts))
    system_prompt = (
        "你是一个问答助手。你必须优先依据提供的上下文回答，"
        "若上下文不足请明确说明不确定。"
    )
    user_prompt = (
        "以下是检索到的上下文：\n"
        f"{context_block}\n\n"
        f"用户问题：{question}\n"
        "请用中文简洁作答。"
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    # 兼容返回格式
    content = getattr(getattr(resp.choices[0], "message", resp.choices[0]), "content", None)
    if not content:
        # 有些兼容实现直接把消息放在 choices[0].message.content
        try:
            content = resp.choices[0].message.content
        except Exception:
            content = ""
    return content or ""


def interactive_with_minimax(retriever) -> None:
    print("已检测到 DASHSCOPE_API_KEY，进入 MiniMax RAG 问答模式（输入 q 退出）。")
    print("可选环境变量：DASHSCOPE_BASE_URL、MINIMAX_MODEL")
    while True:
        q = input("问题(q退出): ")
        if q.strip().lower() in ("q", "quit", "exit"):
            break

        docs = retriever.invoke(q)
        contexts = [d.page_content for d in docs]
        if not contexts:
            print("未检索到相关文档。")
            continue

        out = _answer_with_minimax(q, contexts)
        print("---- 回答 ----")
        print(out)
        print()


def interactive_retrieval_only(retriever) -> None:
    print("未检测到 OPENAI_API_KEY，进入检索演示模式。输入 q 退出。")
    while True:
        q = input("查询(q退出): ")
        if q.strip().lower() in ("q", "quit", "exit"):
            break
        docs = retriever.invoke(q)
        if not docs:
            print("未检索到相关文档。")
            continue
        for i, d in enumerate(docs, start=1):
            print(f"--- 文档片段 {i} ---")
            print(d.page_content)
            print()


def split_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list[str]:
    """简单的按字符分片器（不依赖外部库）。

    Args:
        text: 原始长文本。
        chunk_size: 每个片段最大字符数。
        overlap: 相邻片段的重叠字符数。

    Returns:
        分片后的字符串列表。
    """
    parts: list[str] = []
    if not text:
        return parts
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        parts.append(text[start:end])
        if end == n:
            break
        # 为了避免死循环，确保下一个 start 能前进
        start = max(end - overlap, end - overlap // 2)
    return parts


# 可将下面的长文档作为向量库的输入文本之一（示例来自阿里云百炼 MiniMax 文档）
minimax_doc = """
本文档介绍如何调用阿里云百炼部署的 MiniMax 模型推理服务。

**重要**

本文档仅适用于中国内地地域。如需使用模型，需从中国内地地域[获取API Key](https://help.aliyun.com/zh/model-studio/get-api-key)。

## **模型介绍**

MiniMax-M2.5 是 MiniMax 推出的最新文本模型，擅长编程、办公、文本摘要等任务，且输出速度快，推荐使用。

| **模型名称** | **上下文长度** | **最大输入** | **最大思维链长度+回复长度** > **不支持thinking\\_budget参数** |
| --- | --- | --- | --- |
| **（Token数）** |   |   |
| MiniMax-M2.5 | 204,800 | 196,608 | 131,072 |
| MiniMax-M2.1 | 172,032 | 32,768 |

> 仅支持思考模式。

> 以上模型非集成第三方服务，部署在阿里云百炼服务器上。

## **快速开始**

API 使用前提：已[获取API Key](https://help.aliyun.com/zh/model-studio/get-api-key)并完成[配置API Key到环境变量](https://help.aliyun.com/zh/model-studio/configure-api-key-through-environment-variables)。如果通过SDK调用，需要[安装SDK](https://help.aliyun.com/zh/model-studio/install-sdk#8833b9274f4v8)。

## OpenAI兼容

## Python

### **示例代码**

```
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="MiniMax-M2.5",
    messages=[{"role": "user", "content": "你是谁"}],
    stream=True,
)

reasoning_content = ""  # 完整思考过程
answer_content = ""     # 完整回复
is_answering = False    # 是否进入回复阶段

print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")

for chunk in completion:
    if chunk.choices:
        delta = chunk.choices[0].delta
        # 只收集思考内容
        if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
            if not is_answering:
                print(delta.reasoning_content, end="", flush=True)
            reasoning_content += delta.reasoning_content
        # 收到content，开始进行回复
        if hasattr(delta, "content") and delta.content:
            if not is_answering:
                print("\n" + "=" * 20 + "完整回复" + "=" * 20 + "\n")
                is_answering = True
            print(delta.content, end="", flush=True)
            answer_content += delta.content
```

（此处省略后续示例，为保持文档简洁）
"""

def main() -> None:
    # 使用 minimax_doc 的更细分片作为唯一语料，增加命中概率
    texts = split_text(minimax_doc, chunk_size=800, overlap=200)

    vs = build_vectorstore(texts)
    retriever = vs.as_retriever(search_kwargs={"k": 3})

    # 如果在非交互终端（如 CI / 自动运行），自动演示一次查询并退出
    if not sys.stdin.isatty():
        demo_q = "请简要介绍 MiniMax 模型能做什么？"
        docs = retriever.invoke(demo_q)
        contexts = [d.page_content for d in docs]
        if os.environ.get("DASHSCOPE_API_KEY"):
            out = _answer_with_minimax(demo_q, contexts)
            print("---- 自动示例回答（MiniMax） ----")
            print(out)
            return
        if os.environ.get("OPENAI_API_KEY"):
            out = _answer_with_openai(demo_q, contexts)
            print("---- 自动示例回答（OpenAI） ----")
            print(out)
            return
        print("=== 非交互模式：检索到的文档片段 ===")
        for i, d in enumerate(docs, start=1):
            print(f"--- 文档片段 {i} ---")
            print(d.page_content)
        return

    # 优先使用 DASHSCOPE_API_KEY（调用 MiniMax），其次回退到 OPENAI_API_KEY
    if os.environ.get("DASHSCOPE_API_KEY"):
        interactive_with_minimax(retriever)
    elif os.environ.get("OPENAI_API_KEY"):
        interactive_with_openai(retriever)
    else:
        interactive_retrieval_only(retriever)


if __name__ == "__main__":
    main()
