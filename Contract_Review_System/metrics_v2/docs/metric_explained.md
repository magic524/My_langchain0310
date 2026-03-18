# metrics_v2 指标说明（按代码实现）

本文面向“看报告的人”和“调评测的人”，用尽量直白的方式解释：

- 每个指标到底在算什么
- 为什么会出现 0% 或看起来反直觉的分数
- 看到某种分数组合时应该怎么判断问题

说明依据是当前 `metrics_v2` 的实际计算代码，而不是理想化定义。

## 1. 先看整体流程

评估流程可以概括为 4 步：

1. 选 gold 风险点口径（`adopted_only` 或 `all_labeled`）
2. 把 gold 和预测风险点分别对齐到条款
3. 在同一条款内做风险点一对一匹配
4. 计算条款层、风险点层、结构分、建议分和重合提示

你在报告里看到的两张表，本质上只是第 1 步口径不同，其余计算逻辑一致。

## 2. 两种标签口径

### 2.1 口径 A：`adopted_only`

只把标签里 `status` 为 `accept` 或 `partial` 的风险点当作 gold 正例。

- 适合看“业务最终采纳风险”的覆盖情况
- 对“被拒绝意见”不计入 recall 压力

### 2.2 口径 B：`all_labeled`

把标签中的全部风险点都当作 gold 正例（包括未采纳）。

- 适合看“对全部审查意见”的覆盖情况
- 通常 recall 压力更大

## 3. 对齐和匹配是怎么做的

## 3.1 风险点先对齐到条款（阈值默认 0.33）

对每个风险点，先取一个查询文本：

- 优先 `clause_text`
- 否则 `explanation`
- 再否则 `title`

然后与每个条款的 `clause_text` 计算相似度，选择最高分条款：

- 最高分 >= 条款对齐阈值：算对齐成功
- 最高分 < 阈值：记为 unmatched（会进入告警）

相似度不是单一算法，而是取两者较大值：

- 字符序列相似度（`SequenceMatcher`）
- 中文 token 重叠率

## 3.2 同条款内做一对一风险匹配（阈值默认 0.45）

在每个条款内，用贪心方式匹配：

- 对每个 gold 风险，找当前剩余预测里最相似的一个
- 相似度取 4 个字段相似度最大值：`title`、`explanation`、`suggestion`、`clause_text`
- 若最佳分数 < 风险匹配阈值，则该 gold 记为未匹配
- 已匹配预测会被移除，保证一对一

这一步直接决定风险层 TP/FP/FN。

## 4. 条款层指标（Clause P/R/F1）

条款层只看“该条款有没有风险”，不看条款里风险点数量。

- gold 正例条款：该条款下至少 1 个 gold 风险
- pred 正例条款：该条款下至少 1 个预测风险

然后按二分类统计：

- TP：gold 正例且 pred 正例
- FP：gold 负例但 pred 正例
- FN：gold 正例但 pred 负例

公式：

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2PR / (P + R)

分母为 0 时按 0 处理。

## 5. 风险点层指标（Risk P/R/F1）

风险点层来自“同条款一对一匹配”结果：

- TP = matched_pairs 数量
- FP = unmatched_pred 数量
- FN = unmatched_gold 数量

再套同样二分类公式计算 Precision/Recall/F1。

要点：

- 同一条款报出 1 个风险，不代表该条款所有风险都找全
- 因为是一对一，重复或泛化预测会显著拉低 Precision

## 6. 解释结构分（Explanation Structure）

只对“已匹配风险对”计分，每对满分 1 分，由 4 项平均：

1. `title` 非空且不等于“无”
2. `explanation` 归一化后长度 >= 12
3. `explanation` 含后果/风险类关键词（如“导致、可能、损失、责任、争议、后果、风险”）
4. 有条款绑定信息（`pred.clause_text` 或 `gold.clause_text` 至少一个存在）

最终分数是所有匹配对的平均值；如果没有匹配对，记 0。

## 7. 建议可执行分（Suggestion Actionability）

同样只对“已匹配风险对”计分，每对满分 1 分，由 4 项平均：

1. `suggestion` 非空且不等于“无”
2. `suggestion` 含动作词（如“建议、应、应当、修改、补充、删除、明确、增加、调整”）
3. 预测项有条款绑定（`pred.clause_text` 非空）
4. `suggestion` 归一化后长度 >= 16 且不为“无”

最终取匹配对平均值；无匹配对则记 0。

## 8. 同源重合提示（不计入主分）

### 8.1 Exact Title Overlap

在已匹配风险对中，统计 title 归一化后“完全相同”的比例。

### 8.2 Exact Suggestion Overlap

先过滤掉 gold/pred 任一方建议为空的配对，再统计 suggestion 完全相同的比例。

这两个分数只做风险提示，不参与排名分。

## 9. 跨合同怎么聚合

多份合同汇总时：

- Clause / Risk 的 P/R/F1：先把 TP/FP/FN 在合同间求和，再统一计算（微平均思想）
- 结构分、建议分、重合率：按 `matched_pairs` 加权平均

这意味着：

- 匹配对更多的合同，对结构分和建议分影响更大
- 若整体匹配对很少，这两类分数稳定性会下降

## 10. 告警（Warnings）怎么看

常见两类告警：

- `X gold risks unmatched`：该合同有标签风险没能对齐到任何条款
- `Y predicted risks unmatched`：该参与方有预测风险没能对齐到任何条款

告警多不一定表示模型差，也可能是：

- 原始解析文本噪声较大
- 条款切分与风险文本粒度不一致
- 阈值偏高导致对齐失败

## 11. 为什么会出现 0%

出现整行 0% 常见原因：

1. 预测风险点为空或几乎为空
2. 条款对齐失败很多，导致后续无法进入匹配
3. 风险匹配阈值下没有任何 matched pair
4. 输出多为“无”或占位文本，结构分和建议分也会归零

可先检查：`evaluation_result.json` 中 `matched_pairs`、`unmatched_prediction`、`unmatched_gold`。

## 12. 结果解读建议（实用版）

- Clause Recall 低：先看是否漏筛条款（第一层召回问题）
- Clause Recall 高但 Risk Recall 低：条款找到了，但条款内风险点漏报
- Risk Precision 低：可能过报、重复报、泛化报
- Explanation Structure 低：解释信息不完整，难支撑人工复核
- Suggestion Actionability 低：建议方向可能对，但不可落地
- Exact Overlap 高：注意同源文本抬分风险，避免误判“能力提升”

## 13. 当前版本边界

请将 `metrics_v2` 视为“联调与趋势观察指标”，不要当作严格法律能力排行榜。当前阶段它更适合：

- 快速发现链路问题（解析、抽取、对齐、输出）
- 对比版本迭代是否朝正确方向变化
- 为后续接入更高质量人工标注做接口准备
