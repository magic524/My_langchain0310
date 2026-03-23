# tests

`tests` 是合同审查系统的评测与报告子项目，负责消费 `word2md` 和 `local_llm` 产物，并输出可追溯的评测结果、三方对照和总体汇总。

## 这个子项目负责什么

- 从 `word2md` 的某次输出构建统一数据集
- 解析原合同、第三方审查结果、最终审查意见、采纳说明
- 计算条款级和风险点级指标
- 输出 `evaluation_result.json` 和 `evaluation_report.md`
- 当数据集包含 `local_llm` 参与方时，输出三方对照和总体汇总

## 这个子项目不负责什么

- 不直接调用本地模型 API
- 不维护 prompt 实验脚本
- 不承担原合同批注版导出

## 默认输入输出

- 默认读取：`data/contract_review_outputs/word2md/<batch_name>`
- 默认数据集输出：`Contract_Review_System/tests/outputs/datasets/dataset_<batch_name>.json`
- 默认评测输出：`Contract_Review_System/tests/outputs/eval_runs/<batch_name>/`

## 环境

```powershell
conda activate langchain
```

## 常用命令

### 先构建数据集

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py `
  --input contract_md_260323 `
  --output Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json
```

### 如需显式指定某次 `word2md` 输出目录

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py `
  --input data/contract_review_outputs/word2md/contract_md_260323 `
  --output Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json
```

### 评测传统数据集

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json `
  --output Contract_Review_System/tests/outputs/eval_runs/contract_md_260323
```

### 只评测指定参与方

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json `
  --output Contract_Review_System/tests/outputs/eval_runs/contract_md_260323 `
  --participants third_party,final_applied
```

### 评测 `local_llm` 结果并生成三方对照

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/only_prompt_local_llm/outputs/20260323_local_llm_only_prompt/dataset_with_local_llm.json `
  --output Contract_Review_System/tests/outputs/eval_runs/20260323_local_llm_only_prompt
```

## 核心产物

- `dataset_<batch_name>.json`：统一数据集
- `evaluation_result.json`：完整机器可读评测结果
- `evaluation_report.md`：人工可读评测报告
- `三方对照/`：按合同拆分的三方对照 `md/html/xlsx`
- `总体汇总/`：整体汇总 `md/html/xlsx`

## 目录说明

```text
tests/
├─ docs/
├─ outputs/
├─ scripts/
├─ src/contract_tests/
└─ tests/
```

## 维护约定

- 评测逻辑只依赖 `word2md` 或 `dataset_with_local_llm` 产物
- 如需扩展更多参与方，优先在 `src/contract_tests/` 补齐解析和匹配逻辑
- `only_prompt_local_llm` 只负责生成 `local_llm` 结果与原合同批注版；评测与对照统一放在本项目
