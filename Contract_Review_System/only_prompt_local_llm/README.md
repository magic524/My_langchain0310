# only_prompt_local_llm

`only_prompt_local_llm` 是合同审查系统的本地模型调用子项目，负责用纯 prompt 方式调用本地 OpenAI 兼容 API，并产出 `local_llm` 结果与原合同批注版。

## 这个子项目负责什么

- 读取 `word2md` 的整份合同 Markdown
- 调用本地模型输出结构化风险点
- 把 `local_llm` 预测写回统一数据集
- 生成 `dataset_with_local_llm.json`，供 `tests` 后续评测和生成三方对照
- 生成原合同批注版 Word 文件

## 主入口

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py --run-id 20260317_word2md_eval
```

## 默认输入输出

- 默认读取：`data/contract_review_outputs/word2md/<run_id>`
- 默认输出：`Contract_Review_System/only_prompt_local_llm/outputs/<run_id>_review_bundle_<YYYYMMDD>`

## 环境变量

默认读取：

- `Contract_Review_System/only_prompt_local_llm/.env`

可参考：

- `Contract_Review_System/only_prompt_local_llm/.env.example`

常用字段：

- `OPENAI_LLM_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `OPENAI_TEMPERATURE`
- `OPENAI_EXTRA_BODY`

## 常用命令

全量运行：

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py --run-id 20260317_word2md_eval
```

显式指定输出目录：

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py --run-id 20260317_word2md_eval --output-dir "Contract_Review_System/only_prompt_local_llm/outputs/20260317_word2md_eval_review_bundle_20260323"
```

复用已有模型原始返回，只重跑解析和报告：

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py --run-id 20260317_word2md_eval --reuse-raw-responses
```

只跑一份合同：

```powershell
conda activate langchain
python Contract_Review_System/only_prompt_local_llm/main.py --run-id 20260317_word2md_eval --contract-filter "1-品牌球馆冠名合作协议"
```

## 关键产物

输出根目录下会保留这些核心文件和文件夹：

- `dataset_from_word2md.json`
- `dataset_with_local_llm.json`
- `local_llm_predictions.json`
- `pipeline_summary.json`
- `原合同批注版_local_llm/`
- `raw_responses/`
- `debug_requests/`

## 你关心的最终交付结果

运行完成后，会直接生成：

- `原合同批注版_local_llm`
- `dataset_with_local_llm.json`
- `local_llm_predictions.json`
- `原合同批注版_local_llm`

## 目录示例

```text
Contract_Review_System/only_prompt_local_llm/outputs/<run_id>_review_bundle_<date>/
├── 原合同批注版_local_llm/
├── 三方对照/
│   ├── 1-品牌球馆冠名合作协议_三方对照/
│   ├── 2-服务协议_三方对照/
│   ├── 3-保密协议_三方对照/
│   └── 总体汇总/
├── contract_runs/
├── raw_responses/
└── debug_requests/
```

## 维护约定

- 用户侧统一只看 `main.py`
- 如需调整 prompt、重试逻辑、JSON 兜底解析，修改 `local_model_runner.py`
- 如需调整三方对照表现形式，修改 `tests/src/contract_tests/local_llm_review_pipeline.py` 与 `tests/src/contract_tests/parallel_review_report.py`
