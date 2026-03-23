# only_prompt_local_llm 结构说明

## 推荐修改位置

- 命令入口改 `src/only_prompt_local_llm/cli.py`
- 本地模型主流程改 `src/only_prompt_local_llm/local_model_runner.py`
- 辅助导出逻辑改 `src/only_prompt_local_llm/export_parallel_reports_to_xlsx.py`

## 兼容原则

- `main.py` 继续保留，避免旧命令失效
- 根目录历史模块暂时保留，避免旧入口或旧脚本立刻失效
- 评测、三方对照、总体汇总仍归 `tests/`
