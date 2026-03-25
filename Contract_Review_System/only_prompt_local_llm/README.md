# only_prompt_local_llm

`only_prompt_local_llm` 是合同审查系统中的本地模型调用子项目，负责用纯 prompt 方式调用公司本地 OpenAI 兼容 API，并产出 `local_llm` 结果与原合同批注版。

## 当前目录结构

```text
only_prompt_local_llm/
├─ README.md
├─ main.py
├─ .env.example
├─ docs/
│  └─ structure.md
├─ outputs/
├─ src/
│  └─ only_prompt_local_llm/
│     ├─ __init__.py
│     ├─ cli.py
│     └─ local_model_runner.py
```

同时，本项目依赖共享公共模块：

```text
Contract_Review_System/
├─ .env
└─ common/
   ├─ __init__.py
   └─ local_llm_client.py
```

## 文件职责

- `main.py`
  - 项目根目录主入口
  - 更符合常见项目习惯
  - 内部转发到 `src/only_prompt_local_llm/cli.py`
- `src/only_prompt_local_llm/cli.py`
  - 真正的命令行解析入口
  - 负责 `--input / --output` 等参数解析
  - 通过 `Contract_Review_System/common/local_llm_client.py` 读取共享模型配置
- `src/only_prompt_local_llm/local_model_runner.py`
  - 本地模型主流程
  - 负责读数据集、组装 prompt、解析返回结果并写回数据集
- `docs/structure.md`
  - 结构说明和维护约定

评测和报告后处理现在归 `tests`：

- `Contract_Review_System/tests/src/contract_tests/format_parallel_reports_for_client.py`
- `Contract_Review_System/tests/src/contract_tests/export_parallel_reports_to_xlsx.py`

## 共享本地模型配置

本项目统一读取：

- `Contract_Review_System/.env`

配置模板：

- `Contract_Review_System/.env.example`
- `Contract_Review_System/only_prompt_local_llm/.env.example`

常用字段：

- `OPENAI_LLM_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `OPENAI_TEMPERATURE`
- `OPENAI_EXTRA_BODY`

## 这个子项目负责什么

- 读取 `word2md` 的整份合同 Markdown
- 调用本地模型输出结构化风险点
- 把 `local_llm` 预测写回统一数据集
- 生成 `dataset_with_local_llm.json`
- 生成原合同批注版 Word 文件

## 默认输入输出

- 默认读取：`data/contract_review_outputs/word2md/<batch_name>`
- 默认输出：`Contract_Review_System/only_prompt_local_llm/outputs/<job_name>`

说明：

- `--input`：某次 `word2md` 批次名，或直接传某次 `word2md` 输出目录
- `--output`：本次 local LLM 任务输出目录名，或完整输出目录路径

## 常用命令

### 推荐入口

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input 合同数据md-2026.3.23 `
  --output output_file_name
```

### 显式指定 `word2md` 输出目录

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input data\contract_review_outputs\word2md\合同数据md-2026.3.23 `
  --output try
```

### 复用已有模型原始返回，只重跑解析

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input 合同数据md-2026.3.23 `
  --output output_file_name `
  --reuse-raw-responses
```

## 小测试

### 1. 只测试共享配置是否能读取

```powershell
conda activate langchain
python -c "from Contract_Review_System.common.local_llm_client import load_runtime_config; runtime = load_runtime_config(); print(runtime.model_name); print(runtime.base_url)"
```

### 2. 只跑一个合同做烟测

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input 合同数据md-2026.3.23 `
  --output _tmp_smoke `
  --contract-filter 某个合同关键词
```

如果运行正常，至少应看到这些产物：

- `dataset_with_local_llm.json`
- `local_llm_predictions.json`
- `pipeline_summary.json`

## 后续衔接

本项目完成后，下一步应交给 `tests`：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/only_prompt_local_llm/outputs/output_file_name/dataset_with_local_llm.json `
  --output Contract_Review_System/tests/outputs/eval_runs/output_file_name
```
