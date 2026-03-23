# Contract_Review_System

当前合同审查系统统一整理为三个一级子项目：

## 目录结构

```text
Contract_Review_System/
├── README.md
├── word2md/
├── tests/
└── only_prompt_local_llm/
```

## 三个子项目分别做什么

### 1. `word2md`

负责格式转换。

- 输入：原始 `doc/docx`
- 输出：统一结构的 `output.md + meta.json + run_summary.json`
- 默认输出根目录：`data/contract_review_outputs/word2md`

### 2. `tests`

负责评测与报告底座。

- 输入：`word2md` 的 `run_id`
- 输出：数据集、评测结果、三方对照、总体汇总
- 默认输出根目录：`Contract_Review_System/tests/outputs`

### 3. `only_prompt_local_llm`

负责纯 prompt 的本地模型调用和整包交付产物。

- 输入：`word2md` 的 `run_id`
- 输出：本地模型预测、`dataset_with_local_llm.json`、原合同批注版
- 默认输出根目录：`Contract_Review_System/only_prompt_local_llm/outputs`

## 推荐运行顺序

### 第一步：格式转换

```powershell
conda activate langchain
python Contract_Review_System/word2md/main.py --input-dir data/合同数据-2026.3.12 --recursive --run-id 20260317_word2md_eval
```

### 第二步：如只看传统评测

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py --run-id 20260317_word2md_eval
python Contract_Review_System/tests/scripts/evaluate.py --run-id 20260317_word2md_eval
```

### 第三步：生成本地模型整包产物

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py --run-id 20260317_word2md_eval
```

## 环境约定

统一使用：

```powershell
conda activate langchain
```

## 输出统一约定

现在只有 `word2md` 转换结果写到 `data/contract_review_outputs/`。`tests` 和 `only_prompt_local_llm` 的运行产物都写到各自项目目录下的 `outputs/`。

```text
data/contract_review_outputs/
└── word2md/

Contract_Review_System/tests/outputs/
Contract_Review_System/only_prompt_local_llm/outputs/
```

## 清理原则

- 代码目录只保留长期维护的主线项目
- 一次性实验脚本、临时缓存、旧版试验目录应逐步移除
- 历史 `word2md` 结果统一放到 `data/contract_review_outputs/word2md/` 下管理
- `tests` 和 `only_prompt_local_llm` 的运行产物默认不入库，交给 `outputs/` 和 `.gitignore` 管理
