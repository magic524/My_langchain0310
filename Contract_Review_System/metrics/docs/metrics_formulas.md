# 指标公式说明（Contract Metrics）

本文档对应需求方口径：

- 风险点识别：准确率、漏报率、误报率
- 风险点解释：方向一致性、准确率、完整性
- 风险点修改建议：方向一致性、内容准确率、完整性

## 1. 先说人话：我们到底在算什么

评测单位是“条款级（Clause-level）”。

- 对每个条款，先判断“标签是否认为有风险”（真值）
- 再判断“参与方是否识别为风险”（预测）
- 然后统计 TP/FP/TN/FN，再算识别指标
- 对于识别正确的条款（TP），再算解释和建议质量

默认双口径：

- `policy_a`：标签中 `accept + partial` 作为正例（更贴近“业务采纳”）
- `policy_b`：标签中全部意见都作为正例（更贴近“意见覆盖”）

## 2. 识别指标（最核心）

### 2.1 定义

- `TP`：标签有风险，模型也识别为风险
- `FN`：标签有风险，模型没有识别（漏报）
- `FP`：标签无风险，模型识别成风险（误报）
- `TN`：标签无风险，模型也没识别

### 2.2 公式

- 准确率：`Accuracy = (TP + TN) / (TP + TN + FP + FN)`
- 漏报率：`MissRate = FN / (TP + FN)`
- 误报率：`FalsePositiveRate = FP / (FP + TN)`

分母为 0 时按 0 处理。

### 2.3 真实数据示例（来自当前项目输出）

示例来源：

- 报告文件：`Contract_Review_System/metrics/outputs/eval_runs/20260316_140340/evaluation_report.md`
- 分合同统计（`1-品牌球馆冠名合作协议`，`agent`，`policy_a`）：
  - `TP=7, FP=24, TN=13, FN=4`

代入：

- `Accuracy = (7+13)/(7+24+13+4) = 20/48 = 41.67%`
- `MissRate = 4/(7+4) = 36.36%`
- `FalsePositiveRate = 24/(24+13) = 64.86%`

这组数字的含义：

- 漏报和误报都偏高，说明识别稳定性仍不足。

再看一个你关心的例子（`20260316_153402_one_shot`，`final_applied`，`policy_a`）：

- `TP=3, FN=10`
- `MissRate = 10 / (3 + 10) = 76.92%`

直观解释：

- 标签正例一共 13 个条款，`final_applied` 只命中 3 个，所以漏掉了 10 个。
- 这不是公式问题，而是“`final_applied` 解析结果没有覆盖到足够多的标签风险条款”。

## 3. 解释指标（只在 TP 上算）

只有模型“识别对了风险条款”（TP）才有资格计算解释质量。

### 3.1 方向一致性

规则模式下，比较“标签标题+解释”和“预测标题+解释”的语义相似度：

- 达到阈值（默认 0.35）记 1
- 否则记 0

总体分：`Direction = mean(dir_i)`

### 3.2 解释准确率

`ExplanationAccuracy = mean(sim(label_explanation, pred_explanation))`

其中 `sim` 是规则相似度（文本相似 + 关键词重叠）。

### 3.3 解释完整性

四要素覆盖率：

- 风险类型
- 风险原因
- 条款原文
- 导致后果

单条：`complete_i = (type + reason + clause + consequence) / 4`

总体：`ExplanationCompleteness = mean(complete_i)`

### 3.4 真实样例（来自 TP 配对）

样例来源：

- `Contract_Review_System/metrics/outputs/eval_runs/20260316_140340/evaluation_result.json`
- `contract_id=1-品牌球馆冠名合作协议`
- `participant=agent, policy=policy_a`
- `tp_scored_pairs[0]`

该样例里解释分：

- `direction_consistency = 0.0`
- `accuracy = 0.0`
- `completeness = 0.25`

`0.25` 表示四要素只覆盖了 1 项（1/4）。

## 4. 建议指标（只在 TP 上算）

### 4.1 方向一致性

与解释类似，比较“标签建议”与“预测建议”的方向是否一致：

- 达阈值记 1，否则记 0

### 4.2 内容准确率

`SuggestionAccuracy = mean(sim(label_suggestion, pred_suggestion))`

### 4.3 建议完整性

三部分平均：

- 对标签建议关键内容覆盖（coverage）
- 是否包含可执行动作词（如“建议/应/修改/补充/删除/明确”）
- 是否绑定到对应条款（clause_bind）

`SuggestionCompleteness_i = (coverage + actionability + clause_bind) / 3`

## 5. 聚合规则（跨合同）

- 识别指标：先把所有合同的 `TP/FP/TN/FN` 累加，再统一计算
- 解释/建议指标：按 TP 样本数加权平均

所以合同越多、TP 越多的样本，对总体分影响越大。

## 6. 与原文件的对应关系（可追溯）

以 `md_run_id=20260316_105814` 为例：

- 原合同：`.../1-原合同*/output.md`
- 标签真值（采纳情况）：`.../4-采纳情况说明*/output.md`
- 第三方基线：`.../2-第三方平台审查结果/**/output.md`
- 最终审查：`.../3-最终审查意见*/output.md`
- Agent 预测：`--agent-md` 或 `--agent-json`

建议评测时保留：

- `evaluation_payload.json`
- `evaluation_result.json`
- `evaluation_report.md`
- `evaluation_metrics.csv`

## 7. 关于 final_applied 为什么可能“不高分”

这是常见误解，重点说明：

- `final_applied` 文件通常是“最终合同文本/修订结果”，不一定是“结构化风险清单”。
- 如果把“最终合同正文的编号条款”误当成风险点，会产生大量 FP，分数会异常差。
- 因此 `final_applied` 不天然等于“高分上限”；它更像“结果文档”，不是“标准风险输出格式”。

本项目已在解析层增加过滤：尽量只保留带风险信号（如批注/风险说明/修改建议）的条目，减少这类误判。

## 8. 可选 LLM 裁判

开启 `--use-llm-judge` 后，解释/建议的语义分可由 LLM 输出 0~1。

- 默认关闭（可复现）
- 开启后不改变 `TP/FP/TN/FN` 的统计口径，只增强语义打分
