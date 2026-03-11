# 本地 LLM 对话示例

最小化脚本用于与公司内部部署的 vLLM（OpenAI API 兼容）交互。

准备工作：

- 激活环境（例如你提到的 `conda activate langchain`）。
- 安装依赖：`pip install requests`（如果环境已包含 requests 可跳过）。

环境变量：

- `LOCAL_LLM_API_URL`：本地 vLLM 的 base URL（默认 `http://10.130.61.231:8001/v1`）。
- `LOCAL_LLM_API_KEY`：可选，若服务需要认证则设置。
- `LOCAL_LLM_MODEL`：可选，默认为 `InstructModel`，须与 vLLM 启动时加载的模型名一致。

运行：

```bash
conda activate langchain
pip install requests
python examples/local_LLM/chat_local_llm.py
```

示例：

- 脚本会在交互式终端中读取输入并显示模型回应。
- 若你的 vLLM 使用不同的路由或参数，请参考你们内部 vLLM 文档并调整 `chat_local_llm.py` 中的请求路径或载荷。
