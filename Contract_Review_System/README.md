# Contract_Review_System

当前合同审查系统当前主线整理为 4 个一级子项目：

```text
Contract_Review_System/
├─ README.md
├─ CRSv1/
├─ word2md/
├─ tests/
└─ only_prompt_local_llm/
```

## 子项目职责

### 1. `word2md`

负责格式转换。

- 输入：原始 `doc/docx/pdf`
- 输出：统一结构的 `output.md + meta.json + run_summary.json`
- 默认输出根目录：`data/contract_review_outputs/word2md`

### 2. `CRSv1`

负责正式 v1 审查主链路。

- 输入：某次 `word2md` 结果
- 输出：`crsv1_result.json`、`risk_statistics.json`、`审查报告.md`、`原合同批注版_CRSv1`
- 默认输出根目录：`Contract_Review_System/CRSv1/outputs`

### 3. `only_prompt_local_llm`

负责纯 prompt 的本地模型调用。

- 输入：某次 `word2md` 结果
- 输出：`dataset_with_local_llm.json`、`local_llm_predictions.json`、`原合同批注版_local_llm`
- 默认输出根目录：`Contract_Review_System/only_prompt_local_llm/outputs`

### 4. `tests`

负责评测、三方对照和总体汇总。

- 输入：`word2md` 数据集，或 `only_prompt_local_llm` 产出的 `dataset_with_local_llm.json`
- 输出：数据集、评测结果、三方对照、总体汇总
- 默认输出根目录：`Contract_Review_System/tests/outputs`

## 推荐运行顺序

### 第一步：格式转换

```powershell
conda activate langchain
python Contract_Review_System/word2md/main.py `
  --input data/合同数据-2026.3.12 `
  --recursive `
  --output contract_md_260323
```

说明：

- `--input`：原始合同目录，或单个 `doc/docx/pdf` 文件
- `--output`：本次转换批次名

### 第二步：如只做传统评测

先构建数据集：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py `
  --input contract_md_260323 `
  --output Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json
```

再执行评测：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/tests/outputs/datasets/dataset_contract_md_260323.json `
  --output Contract_Review_System/tests/outputs/eval_runs/contract_md_260323
```

### 第三步：运行 CRSv1 正式审查链路

```powershell
conda activate langchain
python Contract_Review_System/CRSv1/main.py `
  --input contract_md_260323 `
  --output 20260408_crsv1
```

### 第四步：如要继续保留旧版纯 prompt 实验链路

先跑本地模型：

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input contract_md_260323 `
  --output 20260323_local_llm_only_prompt
```

再让 `tests` 评测本地模型结果并生成三方对照：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/only_prompt_local_llm/outputs/20260323_local_llm_only_prompt/dataset_with_local_llm.json `
  --output Contract_Review_System/tests/outputs/eval_runs/20260323_local_llm_only_prompt
```

## 环境约定

统一使用：

```powershell
conda activate langchain
```

## 输出目录约定

现在只有 `word2md` 转换结果写到 `data/contract_review_outputs/`。`tests` 和 `only_prompt_local_llm` 的运行产物都写到各自项目目录下的 `outputs/`，并通过 `.gitignore` 管理。

```text
data/contract_review_outputs/
└─ word2md/

Contract_Review_System/tests/outputs/
Contract_Review_System/only_prompt_local_llm/outputs/
Contract_Review_System/CRSv1/outputs/
```

## 维护原则

- 代码目录只保留长期维护的主线项目
- 一次性实验脚本、临时缓存、旧版试验目录应及时移除
- 历史 `word2md` 结果统一放到 `data/contract_review_outputs/word2md/` 下管理
- `tests` 和 `only_prompt_local_llm` 的运行产物默认不入库
