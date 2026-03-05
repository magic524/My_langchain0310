#!/usr/bin/env python3
"""简易 RAG 演示脚本

说明：
- 若设置了环境变量 `OPENAI_API_KEY`，脚本会使用 OpenAI 生成最终回答（需安装 openai + langchain 支持）。
- 否则脚本只展示检索到的相关文档片段，便于理解检索部分行为。
"""
import os
import sys

def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)

try:
    from langchain.embeddings import HuggingFaceEmbeddings
    from langchain.vectorstores import FAISS
    from langchain.chains import RetrievalQA
    from langchain.llms import OpenAI
except Exception:
    fail("请先安装依赖：pip install -r requirements.txt（在 examples/rag-first-practice 下）")


def build_vectorstore(texts: list[str]):
    """用 sentence-transformers 嵌入 + FAISS 构建向量库"""
    print("正在创建嵌入模型（sentence-transformers/all-MiniLM-L6-v2）...")
    embed = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    print("正在基于文本构建 FAISS 向量索引...")
    vs = FAISS.from_texts(texts, embed)
    return vs


def interactive_with_openai(retriever):
    llm = OpenAI(temperature=0)
    qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=retriever)
    print("已连接 OpenAI，输入问题进行交互（输入 q 退出）。")
    while True:
        q = input("问题(q退出): ")
        if q.strip().lower() in ("q", "quit", "exit"):
            break
        out = qa.run(q)
        print("---- 回答 ----")
        print(out)
        print()


def interactive_retrieval_only(retriever):
    print("未检测到 OPENAI_API_KEY，进入检索演示模式。输入 q 退出。")
    while True:
        q = input("查询(q退出): ")
        if q.strip().lower() in ("q", "quit", "exit"):
            break
        docs = retriever.get_relevant_documents(q)
        if not docs:
            print("未检索到相关文档。")
            continue
        for i, d in enumerate(docs, start=1):
            print(f"--- 文档片段 {i} ---")
            print(d.page_content)
            print()


def main() -> None:
    # 示例文本（起步用，可以替换为真实文档）
    texts = [
        "LangChain 是一个用于构建 LLM 应用的框架，提供了链、工具、检索器和存储等组件。",
        "RAG (Retrieval-Augmented Generation) 的核心思想是先检索相关文档，再由生成模型基于这些文档生成答案，从而提高事实性和上下文长度。",
        "FAISS 是一个高效的相似度搜索库，常用于向量检索场景。",
        "sentence-transformers 提供了许多开箱即用的嵌入模型，例如 all-MiniLM-L6-v2，速度快，表现良好。",
    ]

    vs = build_vectorstore(texts)
    retriever = vs.as_retriever(search_kwargs={"k": 3})

    if os.environ.get("OPENAI_API_KEY"):
        interactive_with_openai(retriever)
    else:
        interactive_retrieval_only(retriever)


if __name__ == "__main__":
    main()
