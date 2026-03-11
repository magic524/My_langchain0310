快速上手 — Build a basic agent

目标：一步步在本地运行一个最简单的 LangChain agent，并让你亲自修改并观察行为变化。

前提
- Python 3.10+
- 已在虚拟环境中（推荐使用 `venv` 或 `uv`）
- 设置好模型提供商的 API Key，例如：
  - Claude (Anthropic): `ANTHROPIC_API_KEY`

安装依赖

```bash
# 从示例目录运行
python -m pip install -r requirements.txt
```

示例代码
- 主脚本：agent.py

运行示例

```bash
# 在 examples/Build-a-basic-agent 目录下
export ANTHROPIC_API_KEY="<your_key_here>"
python agent.py
```

实践练习（逐步指导）
1. 运行脚本，观察输出。
2. 在 `agent.py` 中把 `get_weather` 改成返回更详细的结构化字符串（比如包含温度、湿度）。
3. 修改 `system_prompt`，让 agent 以笑话风格回答问题，重新运行并观察差异。
4. 添加第二个工具函数，例如 `get_time(zone: str)`，将其加入 `tools`，尝试让 agent 调用新工具。

遇到问题
- 如果报错找不到 `langchain`，请确认你安装在当前 Python 环境中。
- 如果模型调用失败，请检查你的 API Key 并查看网络访问权限。

想让我帮你做的下一步？
- 我可以：
  - 运行语法检查并修复小问题（我不能直接执行脚本的网络调用）
  - 将示例扩展为交互式命令行（让你输入查询并持续对话）
  - 增加测试脚本来验证工具函数行为

