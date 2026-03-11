在 LangChain 示例中接入自定义模型 API（逐步指南）

目标
- 使用 `.env` 在本地为 LangChain 示例配置第三方/自定义模型（例如 DashScope/OpenAI 兼容服务、Qwen 等）。
- 修改 `examples/Build-a-basic-agent/agent.py` 使其从环境变量选择模型，并避免 `Unable to infer model provider` 报错。

适用场景
- 你的环境使用如下变量（示例）：
  - `DASHSCOPE_API_KEY=sk-f***a0`
  - `OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`
  - `OPENAI_LLM_MODEL=qwen-plus`
  - `OPENAI_EMBEDDING_MODEL=text-embedding-v4`

文件放置建议
- 可以把 `.env` 放在仓库根目录（即 `/home/magic524/projects/work/langchain/.env`），这样仓库下的所有示例都能读取到同一套环境变量（便于复用）。
- 不要把包含密钥的 `.env` 提交到 Git；在仓库根添加 `.gitignore` 条目：

  .env

步骤（一步步练习）

1) 在仓库根创建 `.env`（示例内容）：

```env
# /home/magic524/projects/work/langchain/.env
DASHSCOPE_API_KEY=sk-f***a0
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_LLM_MODEL=qwen-plus
OPENAI_EMBEDDING_MODEL=text-embedding-v4
# 如果使用 Anthropic/Claude：
# ANTHROPIC_API_KEY=claude_key_here
```

2) 安装依赖（在虚拟环境中执行）：

```bash
python -m pip install -r examples/Build-a-basic-agent/requirements.txt
# 如果你还没装 python-dotenv：
python -m pip install python-dotenv
```

3) 理解 `agent.py` 的工作流程（我已为你修改）：
- 程序会调用 `python-dotenv` 的 `find_dotenv()` 和 `load_dotenv()` 来读取最近的 `.env` 文件。
- 代码会优先使用 `OPENAI_LLM_MODEL`（若存在），其次尝试 `ANTHROPIC_LLM_MODEL` / `MODEL_NAME`，最后回退到示例默认 `claude-sonnet-4-6`。
- 如果你使用 OpenAI 兼容的 endpoint，设置 `OPENAI_API_BASE` 会把该值写入 `os.environ`，以便底层客户端使用。
- 当模型名是 `qwen-plus` 这类不带 provider 前缀的写法时，代码会自动补成 `openai:qwen-plus`，解决 LangChain 无法推断 provider 的报错。
- 当你只配置了 `DASHSCOPE_API_KEY` 时，代码会自动映射到 `OPENAI_API_KEY`（仅在 `OPENAI_API_KEY` 未设置时），便于 OpenAI 兼容模式调用。

4) 运行示例：

```bash
# 从仓库根运行（确保 .env 在仓库根）
python examples/Build-a-basic-agent/agent.py
```

5) 本地调试与验证：
- 如果出现认证错误，请检查相应的密钥变量名（例如 DashScope 需要 `DASHSCOPE_API_KEY`）。
- 你也可以在运行前临时覆盖环境变量：

```bash
export OPENAI_LLM_MODEL="gpt-4o"
python examples/Build-a-basic-agent/agent.py
```

6) 为项目定制（可选练习）
- 在 `examples/Build-a-basic-agent/agent.py` 中把 `create_agent(...)` 的 `model` 参数替换为一个由 `langchain.chat_models.init_chat_model(...)` 返回的已配置模型对象，以便在代码层面传入更多运行时参数（timeout、temperature 等）。
- 如果你使用自建 OpenAI 兼容 endpoint，但遇到证书/网络问题，请尝试调试 `OPENAI_API_BASE`、`OPENAI_API_KEY` 等变量，并检查代理或防火墙设置。

安全建议
- 永远不要在公共仓库中提交 `.env`。
- 使用不同的密钥为不同环境（dev/staging/prod）分隔配置。

附：示例 `.env`（文本便于复制到 Notion）

```text
DASHSCOPE_API_KEY=sk-f***a0
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_LLM_MODEL=qwen-plus
OPENAI_EMBEDDING_MODEL=text-embedding-v4
```

如果你愿意，我可以：
- 把 `agent.py` 再扩展为可交互的 CLI（让你直接在终端输入问题并保留会话）
- 演示如何在代码中初始化一个 `langchain` 的 chat 模型对象（`init_chat_model`），并传递自定义 `base_url` / `api_key` 参数

告诉我你接下来想做哪一项，我会继续引导并做相应修改/演示。
