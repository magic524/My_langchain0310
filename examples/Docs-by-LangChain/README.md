# Docs-by-LangChain 合同审查初版脚本

这个目录下提供了一个“初步探索版”的合同审查脚本，目标是先把以下链路跑通：

- 用户提供一个知识库目录
- 脚本递归读取其中的 `.doc` / `.docx` 文件
- 从历史审查文件中提取正文、批注、修订痕迹
- 对新的合同文件生成同风格的审查批注报告

当前版本刻意保持轻量：

- 不做切片
- 不做 embedding
- 不做向量数据库
- 不把批注直接写回 Word

当前实现是“基于轻量检索 + 大模型生成”的初版，方便后续再演进成完整 RAG。

说明：

- `.docx` 正文提取优先使用 `langchain_community.document_loaders.Docx2txtLoader`（即文档里提到的用法）
- 批注和修订痕迹仍通过解析 Word XML 提取，因为 `Docx2txtLoader` 主要覆盖正文文本

## 文件说明

- `contract_review_agent.py`：主脚本
- `test_contract_review_agent.py`：基础单元测试

## 模型配置

模型环境变量加载方式和 [examples/Build-a-basic-agent/agent.py](../Build-a-basic-agent/agent.py) 保持一致：

- `OPENAI_LLM_MODEL`
- `OPENAI_API_BASE`
- `DASHSCOPE_API_KEY`
- `OPENAI_API_KEY`

脚本会自动执行这些兼容逻辑：

- 若只设置了 `DASHSCOPE_API_KEY`，则自动补到 `OPENAI_API_KEY`
- 若设置了 `OPENAI_API_BASE`，则同时补到 `OPENAI_BASE_URL`
- 若 `OPENAI_LLM_MODEL` 不带 provider 前缀，则自动补成 `openai:<model>`

示例 `.env`：

```env
OPENAI_LLM_MODEL=qwen-plus
OPENAI_API_BASE=https://your-openai-compatible-endpoint/v1
DASHSCOPE_API_KEY=your_api_key
```

## 知识库约定

知识库目录路径由用户在命令行传入。脚本会递归读取其中所有 `.doc` / `.docx`。

建议结构：

```text
your-knowledge-base/
├── 原合同/
│   ├── 合同A.docx
│   └── 合同B.doc
└── 审查/
    ├── 批注版合同A.docx
    ├── 修订版合同A.docx
    └── 其他审查材料.docx
```

路径中包含以下关键词时，脚本会优先把文件识别为“审查材料”：

- `审查`
- `批注`
- `修订`
- `review`
- `comment`
- `revision`

这些材料在检索时会获得更高权重。

## 运行方式

你已经说明本机使用 conda 环境 `langchain`。运行时直接使用这个解释器即可：

```bash
/home/magic524/miniconda3/envs/langchain/bin/python examples/Docs-by-LangChain/contract_review_agent.py \
  --knowledge-dir "/path/to/knowledge-base" \
  --input-file "/path/to/new-contract.docx"
```

如果你希望显式先激活环境，也可以：

```bash
conda activate langchain
python examples/Docs-by-LangChain/contract_review_agent.py \
  --knowledge-dir "/path/to/knowledge-base" \
  --input-file "/path/to/new-contract.docx"
```

可选参数：

```bash
python examples/Docs-by-LangChain/contract_review_agent.py \
  --knowledge-dir "/path/to/knowledge-base" \
  --input-file "/path/to/new-contract.docx" \
  --output "/path/to/review-report.md" \
  --top-k 5 \
  --max-paragraphs 15 \
  --min-paragraph-chars 30
```

## 输出结果

默认会在待审文件旁边生成一个 Markdown 报告：

```text
new-contract.docx.review.md
```

报告包含：

- 待审文件信息
- 知识库统计
- 按条款输出的“风险级别 / 问题说明 / 审查批注 / 建议修改 / 参考依据”
- 每条审查意见对应的参考片段来源

## 当前限制

有两个限制需要提前说明：

1. `.docx` 是完整支持路径，可以提取正文、批注和一部分修订痕迹。
2. `.doc` 是尽力读取模式，当前通过系统 `strings` 命令抽取可读文本，适合初步探索，不适合高精度生产场景。

如果后续要升级到完整版本，建议下一步做：

1. 段落切片和语义检索
2. embedding + 向量库
3. 合同条款级对齐
4. 审查意见结构化输出
5. Word 批注回写和修订模式导出
