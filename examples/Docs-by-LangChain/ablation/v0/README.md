# Ablation v0 — Prompt-only 合同审查实验

目标：只靠 prompt（不使用向量检索或外部知识库）对单个 Word 文档（.doc/.docx）进行审查，输出 Markdown 格式的批注式审查报告。

使用方法：

1. 设置环境变量（或在 `.env` 中配置）：

- `OPENAI_API_BASE`：OpenAI 兼容 HTTP 接口（例如本地 vLLM 服务）的基地址，例如 `http://127.0.0.1:8001/v1`
- `OPENAI_API_KEY`：可选的 API key
- `OPENAI_LLM_MODEL`：模型名称（默认在项目中使用 `InstructModel`）

2. 运行脚本：

```bash
python ablation_v0.py --input-file path/to/your.docx --output review.md
```

输出：会生成一个以 `.ablation.v0.md` 或者你指定的 `--output` 名称的 Markdown 报告。

实现要点：

- 复用了仓库中 `contract_review_agent.py` 的解析函数（`parse_word_file`、`select_target_paragraphs` 等）。
- 通过 `OPENAI_API_BASE + /chat/completions` 接口发送 system+user 消息，仅依赖 prompt 生成审查意见。

注意：对于旧式 `.doc` 文件，脚本会优先尝试转换并解析，若环境不支持转换则会使用 `strings` 做 best-effort 提取。

如需扩展：可以把 `format_references`、知识库检索等逻辑逐步接回以做对照实验。
