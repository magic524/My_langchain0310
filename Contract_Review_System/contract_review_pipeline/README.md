# contract_review_pipeline

`contract_review_pipeline` 是当前合同审查系统的生产链路入口，负责把手工分步执行改成一条自动流水线：

- 输入单个或多个 `doc/docx`
- 自动调用 `word2md`
- 自动把生成的合同 Markdown 全文送入本地模型
- 输出纯 `local_llm_result.json`
- 按照该 JSON 回写原合同批注版 Word

## 目标

这个模块只做生产链路编排，不承担评测数据集拼装职责。

也就是说：

- `word2md` 继续负责格式转换和元信息保留
- `only_prompt_local_llm` 继续负责本地模型推理和 Word 批注导出
- `contract_review_pipeline` 只负责把它们串起来

## 启动方式

```powershell
conda activate langchain
python Contract_Review_System/contract_review_pipeline/main.py `
  --input "data/合同审核系统解决方案_20260331_v1.docx" `
  --output demo_run
```

## 主要产物

输出目录默认位于：

`Contract_Review_System/contract_review_pipeline/outputs/<run_name>/`

至少会生成：

- `local_llm_result.json`
- `<输入文件名>_批注版.docx`
- `_artifacts/`

## 说明

- `run_summary.json` 和 `meta.json` 仍由 `word2md` 保留，用于溯源、复跑和 Word 批注导出
- 纯生产结果统一写到 `local_llm_result.json`
- 顶层默认直接展示批注版 Word 文件，文件名自动跟随输入文件名；重名时自动编号
- 辅助文件统一收纳到 `_artifacts/`，并附带 `文件说明.md`
- 后续如果需要评测，应由 `tests` 或独立评测模块额外读取 `local_llm_result.json` 与第三方结果，再做组装
