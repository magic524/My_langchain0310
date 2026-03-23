# tests 项目流转说明

## 1. 上游输入

`tests` 默认读取：

```text
data/contract_review_outputs/word2md/<batch_name>/
```

这里应至少包含：

- 原合同 Markdown
- 第三方平台审查结果 Markdown
- 最终审查意见 Markdown
- 采纳情况说明 Markdown
- `run_summary.json`

如果上游来自 `only_prompt_local_llm`，则 `tests` 也可以直接读取：

```text
Contract_Review_System/only_prompt_local_llm/outputs/<job_name>/dataset_with_local_llm.json
```

## 2. 数据集构建

运行：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py `
  --input contract_md_260323 `
  --output Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json
```

产物：

```text
Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json
```

## 3. 评测执行

运行：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json `
  --output Contract_Review_System/tests/outputs/eval_runs/contract_md_260323
```

产物：

```text
Contract_Review_System/tests/outputs/eval_runs/contract_md_260323/
├─ evaluation_result.json
├─ evaluation_report.md
├─ 三方对照/
└─ 总体汇总/
```

## 4. 与 `only_prompt_local_llm` 的关系

- `only_prompt_local_llm` 负责生成 `local_llm` 结果、`dataset_with_local_llm.json` 和原合同批注版
- `tests` 负责评测、三方对照和总体汇总
- 如果你只做传统评测，可以只使用 `word2md -> tests`
- 如果你要评测本地模型，则使用 `word2md -> only_prompt_local_llm -> tests`
