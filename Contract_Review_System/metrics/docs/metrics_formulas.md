# 指标公式说明（Contract Metrics）

本文档对应需求方口径：

- 风险点识别：准确率、漏报率、误报率
- 风险点解释：方向一致性、准确率、完整性
- 风险点修改建议：方向一致性、内容准确率、完整性

## 1. 评测对象与口径

系统默认输出两套口径：

- `policy_a`：标签中“采纳 + 部分采纳”为正例
- `policy_b`：标签中“全部意见”为正例（采纳/部分采纳/未采纳/other）

评测粒度：条款级（Clause-level）。

## 2. 风险点识别

对每个条款，定义：

- `y=1`：标签判定为有风险
- `ŷ=1`：模型/参与方判定为有风险

混淆矩阵：

- `TP`：`y=1` 且 `ŷ=1`
- `FN`：`y=1` 且 `ŷ=0`
- `FP`：`y=0` 且 `ŷ=1`
- `TN`：`y=0` 且 `ŷ=0`

公式：

- 准确率 `Accuracy = (TP + TN) / (TP + TN + FP + FN)`
- 漏报率 `MissRate = FN / (TP + FN)`
- 误报率 `FalsePositiveRate = FP / (FP + TN)`

分母为 0 时按 0 处理。

## 3. 风险点解释（仅 TP 条款）

仅在 `TP` 条款上计算。

### 3.1 方向一致性

规则模式下先计算标签与预测在“标题 + 解释文本”上的语义相似度（关键词重合与文本相似度的组合），超过阈值记为 1，否则记为 0。

- 单条得分：`dir_i ∈ {0,1}`
- 总体：`Direction = mean(dir_i)`

### 3.2 准确率

规则模式下使用标签解释与预测解释的文本相似度 `acc_i ∈ [0,1]`。

- 总体：`ExplanationAccuracy = mean(acc_i)`

### 3.3 完整性

解释完整性四要素：

- 风险类型
- 风险原因
- 条款原文
- 导致后果

每条按 4 项覆盖率计分：

`complete_i = (type + reason + clause + consequence) / 4`

- 总体：`ExplanationCompleteness = mean(complete_i)`

## 4. 风险点修改建议（仅 TP 条款）

### 4.1 方向一致性

与解释相同，计算标签建议与预测建议的方向一致性：

- 单条得分：`dir_i ∈ {0,1}`
- 总体：`SuggestionDirection = mean(dir_i)`

### 4.2 内容准确率

计算标签建议与预测建议文本相似度 `content_i ∈ [0,1]`：

- 总体：`SuggestionAccuracy = mean(content_i)`

### 4.3 完整性

建议完整性由三部分组成：

- 对标签建议关键内容覆盖
- 是否包含可执行动作词（如“建议/应/修改/补充/删除/明确”）
- 是否绑定到对应条款

`SuggestionCompleteness_i = (coverage + actionability + clause_bind) / 3`

- 总体：`SuggestionCompleteness = mean(SuggestionCompleteness_i)`

## 5. 聚合规则

- 合同内先按条款计算。
- 合同间聚合：
  - 识别指标：先汇总 `TP/FP/TN/FN` 再计算
  - 解释/建议指标：按 `TP` 样本数加权平均

## 6. 可选 LLM 裁判

当开启 `--use-llm-judge` 时，方向一致性/准确率/完整性可由 LLM 输出 0~1 分。

- 默认关闭（保证可复现）
- 开启后只影响语义维度分数，不改变 `TP/FP/TN/FN` 的统计口径
