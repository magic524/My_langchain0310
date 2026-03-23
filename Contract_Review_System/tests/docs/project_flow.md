# tests 项目流转说明

## 1. 上游输入

`tests` 默认读取：

```text
data/contract_review_outputs/word2md/<run_id>/
```

这里应至少包含：

- 原合同 Markdown
- 第三方平台审查结果 Markdown
- 最终审查意见 Markdown
- 采纳情况说明 Markdown
- `run_summary.json`

## 2. 数据集构建

运行：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py --run-id 20260317_word2md_eval
```

产物：

```text
Contract_Review_System/tests/outputs/datasets/dataset_<run_id>.json
```

## 3. 评测执行

运行：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py --run-id 20260317_word2md_eval
```

产物：

```text
Contract_Review_System/tests/outputs/eval_runs/<run_id>/
├── evaluation_result.json
└── evaluation_report.md
```

## 4. 与 only_prompt_local_llm 的关系

- `tests` 提供底层数据集、匹配、评测、报告能力
- `only_prompt_local_llm` 在本项目能力基础上补充本地模型预测、三方对照、总体汇总、原合同批注版导出
- 如果你只是验证第三方平台和最终审查意见的传统评测，停在本项目即可
