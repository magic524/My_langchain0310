# Contract Metrics 子项目

本子项目用于合同审查效果评测，代码独立于 `v1` 与 `datatype_test`，只复用 `datatype_test/outputs_md/{run_id}` 的 Markdown 产物。

- 标签与基线来源：`Contract_Review_System/datatype_test/outputs_md/{run_id}`
- Agent 输入：`JSON + Markdown`
- 默认对比对象：`third_party`、`final_applied`、`agent`
- 默认双口径：
  - `policy_a`：采纳 + 部分采纳为正例
  - `policy_b`：全部意见为正例

当前阶段推荐评测“只依赖 Prompt”的模型能力，不评测 `v1` 的知识库检索模式。

## 环境与依赖

```powershell
conda activate langchain
pip install -r Contract_Review_System/metrics/requirements.txt
```

Prompt-only 模型连接（OpenAI 兼容）默认读取：

- `Contract_Review_System/metrics/.env`（优先）
- 当前工作目录向上查找的 `.env`（兜底）

关键变量与 `v1/scripts/run_ablation.py` 保持同风格：

- `OPENAI_LLM_MODEL`
- `OPENAI_API_BASE`（会拼接 `/chat/completions`）
- `OPENAI_API_KEY`
- `OPENAI_TEMPERATURE`
- `OPENAI_EXTRA_BODY`（JSON 字符串）

## 快速开始（Prompt-Only 推荐）

### 0) 一条命令跑完（推荐）

```powershell
python Contract_Review_System/metrics/scripts/run_prompt_eval.py \
  --md-run-id 20260316_105814 \
  --participants third_party,final_applied,agent
```

这条命令会自动完成：

- 构建数据集
- 用 prompt-only 方式逐条款调用模型生成 `agent` 审查结果
- 计算三方指标（第三方 / 最终审查 / agent）
- 输出 `evaluation_report.md`、`evaluation_result.json`、`evaluation_metrics.csv`
- 额外输出 `RUN_TRACE.md`（运行参数与模型配置快照）和 `MISS_ANALYSIS.md`（漏报样例）

### 1) 构建数据集

```powershell
python Contract_Review_System/metrics/scripts/build_dataset.py --md-run-id 20260316_105814
```

输出：

```txt
Contract_Review_System/metrics/outputs/datasets/dataset_20260316_105814.json
```

### 2) 评测 Agent（独立输入，不依赖 v1 目录）

```powershell
python Contract_Review_System/metrics/scripts/evaluate.py \
  --dataset Contract_Review_System/metrics/outputs/datasets/dataset_20260316_105814.json \
  --agent-md Contract_Review_System/metrics/inputs/agent/review_report.md \
  --participants third_party,agent
```

说明：

- `--participants third_party,agent`：现阶段常用对比（第三方 vs 你的 prompt-only Agent）。
- 若需要加入最终审查意见对比，可改为 `--participants third_party,final_applied,agent`。
- 也可用 `--agent-json` 输入结构化结果。

### 2.1) Prompt-Only 一键脚本（推荐）

```powershell
python Contract_Review_System/metrics/scripts/evaluate_prompt_only.py \
  --md-run-id 20260316_105814 \
  --agent-md Contract_Review_System/metrics/inputs/agent/review_report.md
```

默认参与方：`third_party,agent`。

### 3) 生成报告

```powershell
python Contract_Review_System/metrics/scripts/report.py \
  --evaluation-json Contract_Review_System/metrics/outputs/eval_runs/<run_id>/evaluation_payload.json
```

输出：

- `evaluation_report.md`：可读主报告（双口径 + 分合同 + 告警）
- `evaluation_result.json`：完整细节（含条款级匹配与 TP 样本打分）
- `evaluation_metrics.csv`：扁平指标表，便于画图或汇总
- `README_summary.md`：本次 run 的输入/参与方/开关简要留痕

## 文件作用总览

### 根目录文件

- `requirements.txt`：本子项目依赖列表。
- `README.md`：项目说明、命令、文件职责。

### `inputs/`

- `inputs/agent/`：放置 Agent 预测输入文件（推荐放 `review_report.md` 或 JSON）。
- `inputs/agent/AGENT_INPUT_TEMPLATE.md`：Markdown 输入模板（便于按约定格式输出）。

### `config/`

- `defaults.json`：默认评测配置（参与方、匹配阈值、规则判分阈值、是否启用 LLM 裁判）。

### `docs/`

- `metrics_formulas.md`：指标公式与通俗解释，对应需求方口径。
- `data_mapping.md`：原合同/第三方/采纳/最终审查如何映射成评测样本。
- `result_interpretation.md`：如何解读 `evaluation_report.md` 与常见问题定位。

### `scripts/`（命令入口）

- `build_dataset.py`：从 `outputs_md/{run_id}` 解析并生成统一数据集 JSON。
- `evaluate.py`：读取数据集 + Agent 预测，计算双口径评测结果。
- `report.py`：把 `evaluation_payload.json` 渲染成 md/json/csv 报告。
- `evaluate_prompt_only.py`：prompt-only 专用入口（可自动构建数据集并直接产出报告）。
- `run_prompt_eval.py`：一条命令完成“建集-推理-评测-出报告”（推荐日常使用）。

### `src/contract_metrics/`（核心模块）

- `__init__.py`：包入口导出。
- `types.py`：核心数据结构（合同、条款、风险点、指标等 dataclass）。
- `io_utils.py`：文件读写、路径与文本 I/O 工具。
- `text_utils.py`：文本归一化、相似度、关键字覆盖等通用文本函数。
- `parse_utils.py`：通用解析辅助（标题/段落切分、字段抽取工具）。
- `clause_parser.py`：从合同 Markdown 抽取条款级单元。
- `label_parser.py`：解析“采纳情况说明”，并标准化状态为 `accept/partial/reject/other`。
- `baseline_parser.py`：解析第三方与最终审查文件，按优先级自动选文件。
- `prediction_adapter.py`：适配 Agent 输入（JSON schema / Markdown 规则解析）。
- `matcher.py`：标签与预测映射到条款级单元，产出匹配与 unmatched 信息。
- `judge.py`：解释/建议判分器（规则判分 + 可选 LLM 裁判）。
- `scorer.py`：计算识别、解释、建议三类指标与 TP 样本打分。
- `dataset_builder.py`：组装统一数据集并输出 `dataset_*.json`。
- `evaluator.py`：评测流程编排（读配置、调用 adapter/matcher/scorer）。
- `reporter.py`：生成 `evaluation_report.md`、`evaluation_result.json`、`evaluation_metrics.csv`、`README_summary.md`。
- `config.py`：加载并校验配置文件，形成运行时配置对象。

### `tests/`

- `conftest.py`：pytest 公共 fixture 与测试初始化。
- `unit_tests/test_baseline_parser.py`：第三方/最终审查解析过滤规则单测。
- `unit_tests/test_label_parser.py`：采纳状态与标签抽取单测。
- `unit_tests/test_matcher.py`：条款匹配与 TP/FP/FN/TN 统计单测。
- `unit_tests/test_prediction_adapter.py`：JSON/Markdown 预测解析单测。
- `unit_tests/test_scorer.py`：指标公式与完整性判分单测。

### `outputs/`（运行产物）

- `outputs/datasets/dataset_<run_id>.json`：统一评测数据集。
- `outputs/eval_runs/<run_id>/evaluation_payload.json`：评测原始结果载荷。
- `outputs/eval_runs/<run_id>/evaluation_report.md`：主报告。
- `outputs/eval_runs/<run_id>/evaluation_result.json`：详细结果。
- `outputs/eval_runs/<run_id>/evaluation_metrics.csv`：指标表。
- `outputs/eval_runs/<run_id>/README_summary.md`：run 级摘要。
- `outputs/eval_runs/<run_id>/RUN_TRACE.md`：运行留痕（输入参数、模型配置快照、告警、产物路径）。
- `outputs/eval_runs/<run_id>/MISS_ANALYSIS.md`：按参与方/口径列出漏报率与 FN 条款样例。

## Agent JSON 输入协议

建议结构：

```json
{
  "contracts": [
    {
      "contract_id": "1-品牌球馆冠名合作协议",
      "risks": [
        {
          "title": "主体信息不完整",
          "clause_text": "统一社会信用代码/身份证号：",
          "explanation": "该字段为空会导致主体不明，影响送达和诉讼。",
          "suggestion": "补充统一社会信用代码并核验营业执照。",
          "has_risk": true
        }
      ]
    }
  ]
}
```

## 说明

- 规则判分默认开启，LLM 裁判默认关闭。
- 可用 `--use-llm-judge` 启用 LLM 裁判（需要 `.env` OpenAI 兼容配置）。
- `other` 状态不强行归类，在报告中单列并进入“需人工复核”范围。
