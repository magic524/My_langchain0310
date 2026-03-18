# metrics_v2

`metrics_v2` 是一个独立的小型评估项目，用来评估合同审查系统在当前 3 份样本数据上的基础表现。

它和旧版 `metrics` 的关系：

- 目录平级
- 代码独立
- 不互相 import
- 默认只依赖 Python 标准库

## 设计目标

当前数据条件非常有限：

- 只有 `data/合同数据-2026.3.12` 这 3 个案例
- 没有人工逐条真值
- 只有“采纳情况说明”可作为近似 gold label
- `third_party` 与标签存在明显同源风险

因此 `metrics_v2` 的目标不是做“学术级严格评测”，而是先做一套更符合直觉、可追溯、可继续演进的评估底座。

核心原则：

1. 先保证评测结果可解释。
2. 先保证数据流透明。
3. 先保证和未来本地 agent 的输入结构一致。

## 当前评估思路

### 1. 数据输入

默认读取：

- `Contract_Review_System/v2/word2md/outputs_md/<run_id>`

并从中识别每个合同的：

- 原合同 markdown
- 第三方平台 markdown
- 最终审查意见 markdown
- 采纳情况说明 markdown

### 2. 最小上下文单元

数据集中的每个条款单元会保留：

- 当前条款全文
- 所属章节标题
- 上一条款摘要
- 下一条款摘要
- 可直接提供给模型的 `context_text`

这个设计是为了后续本地 agent 能直接接入，不再走“一句话一句话切碎”的方式。

补充说明：

- `metrics_v2` 同时保留整份合同的 `full_contract_text`
- 也保留条款块 `clauses`

也就是说：

- 如果 mentor 要求“整份合同 markdown 全文送入模型”，这是支持的
- 条款块的作用主要是评估归因和后续 agent 演进
- 不是强制要求当前测试阶段一定按块推理

### 3. 指标分层

目前默认产出以下几类指标：

- 条款层识别
  - `Clause Precision`
  - `Clause Recall`
  - `Clause F1`
- 风险点层识别
  - `Risk Precision`
  - `Risk Recall`
  - `Risk F1`
- 解释结构分
  - 更关注是否说清楚原因、后果、是否绑定到条款
- 建议可执行分
  - 更关注建议是否非空、是否可执行、是否绑定条款
- 同源重合提示
  - `Exact Title Overlap`
  - `Exact Suggestion Overlap`

## 目录结构

```text
metrics_v2/
├── docs/
├── outputs/
├── scripts/
├── src/
│   └── contract_metrics_v2/
└── tests/
```

## 使用方式

### 1. 先构建数据集

```bash
python Contract_Review_System/metrics_v2/scripts/build_dataset.py --run-id 20260317_word2md_eval
```

### 2. 再运行评估

```bash
python Contract_Review_System/metrics_v2/scripts/evaluate.py --run-id 20260317_word2md_eval
```

### 3. 一步运行

```bash
python Contract_Review_System/metrics_v2/scripts/run_demo.py --run-id 20260317_word2md_eval
```

## 产物说明

默认输出到：

- `Contract_Review_System/metrics_v2/outputs/datasets/`
- `Contract_Review_System/metrics_v2/outputs/eval_runs/<run_id>/`

主要文件：

- `dataset_<run_id>.json`
- `evaluation_result.json`
- `evaluation_report.md`

## 文档索引

- [指标说明（按代码实现）](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics_v2/docs/metric_explained.md)
- [指标设计说明](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics_v2/docs/metric_design.md)
- [项目流程说明](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics_v2/docs/project_flow.md)
