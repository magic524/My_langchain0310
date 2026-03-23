# only_prompt_local_llm

`only_prompt_local_llm` 是合同审查系统的本地模型调用子项目，负责用纯 prompt 方式调用本地 OpenAI 兼容 API，并产出 `local_llm` 结果与原合同批注版。

## 当前目录结构

```text
only_prompt_local_llm/
├─ README.md
├─ .env
├─ .env.example
├─ docs/
│  └─ structure.md
├─ outputs/
├─ scripts/
│  └─ main.py
├─ src/only_prompt_local_llm/
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ local_model_runner.py
│  └─ export_parallel_reports_to_xlsx.py
├─ main.py
├─ local_model_runner.py
└─ export_parallel_reports_to_xlsx.py
```

## 每个文件是干嘛的

### 推荐使用的目录

- `scripts/main.py`
  - 推荐命令入口
  - 以后优先从这里启动
- `src/only_prompt_local_llm/cli.py`
  - 真正的命令行解析入口
  - 负责 `--input / --output` 等参数解析
- `src/only_prompt_local_llm/local_model_runner.py`
  - 本地模型主流程
  - 负责读数据集、组装 prompt、调用本地 API、解析返回结果
- `src/only_prompt_local_llm/export_parallel_reports_to_xlsx.py`
  - Markdown 表格转 `xlsx`
  - 当前主要供历史兼容和辅助导出使用
- `docs/structure.md`
  - 结构说明和维护约定

### 兼容保留的文件

- `main.py`
  - 兼容旧入口
- `local_model_runner.py`
  - 历史主流程文件
  - 后续建议只改 `src/only_prompt_local_llm/local_model_runner.py`
- `export_parallel_reports_to_xlsx.py`
  - 历史辅助脚本
- `.env`
  - 本地模型配置
- `.env.example`
  - 配置模板

## 这个子项目负责什么

- 读取 `word2md` 的整份合同 Markdown
- 调用本地模型输出结构化风险点
- 把 `local_llm` 预测写回统一数据集
- 生成 `dataset_with_local_llm.json`，供 `tests` 后续评测和生成三方对照
- 生成原合同批注版 Word 文件

## 这个子项目不负责什么

- 不负责三方对照
- 不负责总体汇总
- 不负责最终评测报告

## 默认输入输出

- 默认读取：`data/contract_review_outputs/word2md/<batch_name>`
- 默认输出：`Contract_Review_System/only_prompt_local_llm/outputs/<job_name>`

说明：

- `--input`：某次 `word2md` 批次名，或直接传某次 `word2md` 输出目录
- `--output`：本次 local LLM 任务输出目录名，或完整输出目录路径

## 环境变量

- `.env`：当前实际运行配置
- `.env.example`：新环境初始化时的参考模板

常用字段：

- `OPENAI_LLM_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `OPENAI_TEMPERATURE`
- `OPENAI_EXTRA_BODY`

## 常用命令

### 推荐入口

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/scripts/main.py `
  --input contract_md_260323 `
  --output 20260323_local_llm_only_prompt
```

### 兼容旧入口

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input contract_md_260323 `
  --output 20260323_local_llm_only_prompt
```

### 显式指定 `word2md` 输出目录

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/scripts/main.py `
  --input data/contract_review_outputs/word2md/contract_md_260323 `
  --output 20260323_local_llm_only_prompt
```

### 复用已有模型原始返回，只重跑解析

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/scripts/main.py `
  --input contract_md_260323 `
  --output 20260323_local_llm_only_prompt `
  --reuse-raw-responses
```

## 关键产物

- `dataset_from_word2md.json`
- `dataset_with_local_llm.json`
- `local_llm_predictions.json`
- `pipeline_summary.json`
- `原合同批注版_local_llm/`
- `raw_responses/`
- `debug_requests/`

## 后续衔接

本项目完成后，下一步应交给 `tests`：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/only_prompt_local_llm/outputs/20260323_local_llm_only_prompt/dataset_with_local_llm.json `
  --output Contract_Review_System/tests/outputs/eval_runs/20260323_local_llm_only_prompt
```
