# only_prompt_local_llm

`only_prompt_local_llm` 是合同审查系统里的本地模型实验子项目，负责用纯 prompt 方式调用本地 OpenAI 兼容接口，并产出 `local_llm` 审查结果与原合同批注版。

## 职责边界

这个子项目负责：

- 读取某次 `word2md` 输出
- 构建本项目需要的数据集视图
- 调用本地模型生成结构化风险点
- 写出 `dataset_with_local_llm.json`
- 支持输出纯生产结果 `local_llm_result.json`
- 写出 `local_llm_predictions.json`
- 导出原合同批注版 Word 文档

这个子项目不负责：

- 评测指标计算
- 三方对照与总体汇总
- 客户报告导出

这些后处理统一归 `Contract_Review_System/tests` 管理。

## 当前目录结构

```text
only_prompt_local_llm/
├─ README.md
├─ .env
├─ main.py
├─ docs/
│  └─ structure.md
├─ outputs/
├─ src/
│  └─ only_prompt_local_llm/
│     ├─ __init__.py
│     ├─ baseline_parser.py
│     ├─ clause_parser.py
│     ├─ cli.py
│     ├─ dataset_builder.py
│     ├─ io_utils.py
│     ├─ label_parser.py
│     ├─ local_model_runner.py
│     ├─ parse_utils.py
│     ├─ review_types.py
│     ├─ text_utils.py
│     └─ word_comment_export.py
└─ __pycache__/
```

说明：
- `__pycache__/` 是运行缓存，不属于需要维护的源码结构。
- 真正需要维护的是 `src/only_prompt_local_llm/` 下的源码文件。

## 关键文件说明

- `main.py`
  - 项目根目录入口
  - 转发到 `src/only_prompt_local_llm/cli.py`
- `src/only_prompt_local_llm/cli.py`
  - 命令行入口
  - 负责解析输入输出路径并组织产物落盘
- `src/only_prompt_local_llm/local_model_runner.py`
  - 本地模型调用主流程
  - 负责 prompt、请求、回包解析和 `local_llm` 风险结果生成
- `src/only_prompt_local_llm/dataset_builder.py`
  - 从 `word2md` 结果构建本项目需要的数据集
- `src/only_prompt_local_llm/word_comment_export.py`
  - 负责把 `local_llm` 风险写回原合同 Word 批注
- `src/only_prompt_local_llm/review_types.py`
  - 本项目内部使用的数据结构定义
- `src/only_prompt_local_llm/baseline_parser.py`
  - 解析第三方审查结果和最终审查结果
- `src/only_prompt_local_llm/clause_parser.py`
  - 提取原合同条款块
- `src/only_prompt_local_llm/label_parser.py`
  - 解析采纳情况说明
- `src/only_prompt_local_llm/io_utils.py`
  - 读写文件和路径解析辅助
- `src/only_prompt_local_llm/parse_utils.py`
  - Markdown 解析辅助
- `src/only_prompt_local_llm/text_utils.py`
  - 文本清洗和匹配辅助

## 运行环境

```powershell
conda activate langchain
```

共享配置读取：

- `Contract_Review_System/.env`
- `Contract_Review_System/.env.example`

当前项目目录下也有：

- `Contract_Review_System/only_prompt_local_llm/.env`

常用字段：

- `OPENAI_LLM_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `OPENAI_TEMPERATURE`
- `OPENAI_EXTRA_BODY`

## 常用命令

### 按批次名运行

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input contract_md_260323 `
  --output 20260323_local_llm_only_prompt
```

### 显式指定 `word2md` 输出目录

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input data/contract_review_outputs/word2md/contract_md_260323 `
  --output try
```

### 复用已有模型原始返回

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input contract_md_260323 `
  --output rerun_parse_only `
  --reuse-raw-responses
```

### 只跑单个合同做烟测

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py `
  --input contract_md_260323 `
  --output _tmp_smoke `
  --contract-filter 某个合同关键词
```

## 默认产物

默认输出到：`Contract_Review_System/only_prompt_local_llm/outputs/<job_name>`

至少会生成这些文件：

- `dataset_from_word2md.json`
- `dataset_with_local_llm.json`
- `local_llm_result.json`
- `local_llm_predictions.json`
- `pipeline_summary.json`
- `原合同批注版_local_llm/`

## 后续衔接

本项目完成后，如需评测和三方对照，继续调用 `tests`：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py `
  --input Contract_Review_System/only_prompt_local_llm/outputs/20260323_local_llm_only_prompt/dataset_with_local_llm.json `
  --output Contract_Review_System/tests/outputs/eval_runs/20260323_local_llm_only_prompt
```
