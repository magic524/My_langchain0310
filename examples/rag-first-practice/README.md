快速上手 RAG（检索增强生成）示例

概览
- 本示例演示如何用一个本地嵌入模型 + 向量库做检索（Retrieval），并可选地使用 OpenAI 生成最终答案（Generation）。

准备
1. 创建并激活 Python 虚拟环境（推荐 Python 3.10+）。
2. 在示例目录中安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

运行示例
- 如果你有 `OPENAI_API_KEY` 并想让模型生成答案：

```bash
export OPENAI_API_KEY="sk-..."
python rag_example.py
```

- 如果没有 OpenAI Key，脚本会展示检索到的相关文档片段：

```bash
python rag_example.py
```

说明
- `rag_example.py` 会：
  - 使用 `sentence-transformers/all-MiniLM-L6-v2` 生成嵌入；
  - 用 FAISS 构建向量索引并做相似度检索；
  - 若检测到 `OPENAI_API_KEY`，则使用 OpenAI 进行 RAG 风格的问答；否则只展示检索结果。

后续建议
- 尝试把文档换成你的笔记、PDF（先用文本提取），并对比不同检索 `k` 值的效果。
- 可尝试将生成模型换为本地小型 LLM（如 `llama.cpp` 后端或 HuggingFace text-generation 模型）。
