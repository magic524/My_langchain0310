# only_prompt_local_llm 结构说明

## 推荐修改位置

- 命令入口改 `src/only_prompt_local_llm/cli.py`
- 本地模型主流程改 `src/only_prompt_local_llm/local_model_runner.py`
- 评测报告格式化改 `Contract_Review_System/tests/src/contract_tests/format_parallel_reports_for_client.py`
- 评测报告导出 xlsx 改 `Contract_Review_System/tests/src/contract_tests/export_parallel_reports_to_xlsx.py`

## 兼容原则

- `main.py` 继续保留，避免旧命令失效
- 评测、三方对照、总体汇总仍归 `tests/`
