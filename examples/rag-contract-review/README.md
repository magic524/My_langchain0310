# RAG 合同审查 示例

这是一个最小可运行示例，演示如何对 DOCX（含批注/comments）使用 RAG（检索增强生成）来做合同审查。

主要功能
- 从 DOCX 中抽取主文件文本和批注（comments.xml），并合并为检索文档。
- 使用 OpenAI Embeddings + FAISS 建索引（可替换为其他嵌入器或向量库）。
- 使用 RetrievalQA 与 LLM（示例使用 ChatOpenAI）进行问答，输出风险点与改进建议。

快速开始（WSL）

1. 在 WSL 中激活你的 conda 环境（你已说明使用 `conda activate langchain`）。

2. 安装示例依赖（如果需要）：

```bash
pip install -r examples/rag-contract-review/requirements.txt
```

3. 运行示例（示例会自动把 Windows 风格路径转换为 WSL 风格）：

```bash
python examples/rag-contract-review/contract_rag.py "E:\\Work\\AI合同审查系统0310\\合同数据-2026.3.6\\...\\批注版-品牌球馆冠名合作协议.docx"
```

注意：脚本会把 `E:\\...` 转为 `/mnt/e/...`，也可以直接传入 WSL 路径。

4. 首次索引会把向量存到 `--index_dir` （默认为 `./contract_index`），下次会加载现成索引。

自定义
- 如需使用其他嵌入器/LLM（本地或私有模型），修改 `get_llm()` 与 `build_vectorstore()` 中的实现。

环境变量 / .env
 - 脚本支持通过环境变量配置 OpenAI 兼容的服务（例如千问），并支持 `.env` 文件。示例 `.env`：

```text
OPENAI_API_KEY=your_openai_format_api_key
OPENAI_API_BASE=https://your-qianwen-host.example.com/v1
OPENAI_LLM_MODEL=qianwen-chat-model-name
OPENAI_EMBEDDING_MODEL=qianwen-embedding-model-name
```

使用方式（两种可选）：

- 直接 export（当前 shell 会话）：

```bash
export OPENAI_API_KEY=your_openai_format_api_key
export OPENAI_API_BASE=https://your-qianwen-host.example.com/v1
```

- 或在项目根放一个 `.env` 文件（脚本会自动加载）。

命令行覆盖：可以在运行时用 `--llm-model` 和 `--embed-model` 参数覆盖 `.env` 中的设置：

```bash
python examples/rag-contract-review/contract_rag.py /mnt/e/.../file.docx --llm-model qianwen-chat-model-name --embed-model qianwen-embedding-model-name
```

后续建议
- 调整分块策略、索引持久化、以及针对合同的定制 prompt（例如要输出风险等级、相关条款定位、修订建议等）。

如果你希望，我可以：
- 运行一次示例（请确认你在 WSL 中并且已激活环境）
- 将 prompt 模板改为中文的“风险点 + 改进建议 + 关键条款定位”格式
- 用 Chroma/other vectorstore 替换 FAISS 或添加向量数据库持久化示例
