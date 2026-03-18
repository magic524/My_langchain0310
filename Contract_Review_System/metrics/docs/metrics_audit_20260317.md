# 指标审计与重构建议（2026-03-17）

本文针对以下现状做审计：

- 指标公式文档：[metrics_formulas.md](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/docs/metrics_formulas.md)
- 最新报告：[evaluation_report.md](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/20260317_word2md_eval/evaluation_report.md)
- 最新明细结果：`evaluation_result.json`
- 最新数据集：`dataset_20260317_word2md_eval.json`

结论先行：

1. 当前 `Accuracy / Miss Rate / False Positive Rate` 的数学公式本身没有明显写错。
2. 当前评估口径不适合直接回答“本地 agent 能否比肩 Alpha GPT”。
3. `third_party` 的解释和建议高分大多不是能力证明，而是标签与第三方结果高度同源导致的“泄漏式高分”。
4. 当前“条款级二分类”会压扁一个条款中的多个风险点，不足以评估合同审查系统真正需要的“风险点枚举完整度”。

## 1. 本次发现的核心问题

### 1.1 标签与第三方结果高度同源，导致对比失真

对 `dataset_20260317_word2md_eval.json` 做抽样和计数后，3 个合同都出现了同样现象：

- `1-品牌球馆冠名合作协议`
  - labels = 20
  - third_party = 32
  - exact title overlap = 20
  - exact suggestion overlap = 20
- `2-服务协议`
  - labels = 14
  - third_party = 26
  - exact title overlap = 14
  - exact suggestion overlap = 14
- `3-保密协议`
  - labels = 6
  - third_party = 18
  - exact title overlap = 6
  - exact suggestion overlap = 6

这说明当前标签中的全部风险标题，和第三方平台输出中的一部分标题是逐条完全一致的；标签中的建议文本也与第三方平台逐条完全一致。

因此：

- `third_party` 不是一个和标签独立的参照物
- `third_party` 的解释分和建议分不能作为“能力逼近标签”的可靠证据
- 现有口径更像是在验证“第三方结果是否被原样保留进标签文档”

### 1.2 `policy_b` 出现 100% 并不奇怪，根因是“同源标签 + 条款级命中”

当前总表里：

- `third_party / policy_b`
  - `TP=28, FP=0, TN=49, FN=0`
  - `Accuracy=100%`
  - `Miss Rate=0%`
  - `False Positive Rate=0%`

这组结果在当前实现下是自洽的，但不代表评测合理。

原因是：

- `policy_b` 把标签中的全部意见都当正例
- 当前标签和 `third_party` 高度同源
- 当前识别层只判断“该条款是否存在任一风险”，而不是“该条款内风险点是否一一对应”

只要第三方在同一条款上命中了至少一个风险，就会被记成 `TP`。即使该条款其实有多个风险点，且第三方只覆盖其中一部分，也不会在识别层被继续扣分。

### 1.3 当前评测单位过粗：条款级二分类会掩盖“漏掉部分风险点”

当前实现位于 [scorer.py](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/src/contract_metrics/scorer.py)。

它对每个条款只做一次判断：

- 标签有无风险
- 预测有无风险

这会带来两个问题：

1. 一个条款里有 2 到 3 个风险点时，只要模型报出其中 1 个，就算该条款识别成功。
2. 模型在同一条款中多报 3 个错误风险，也不会额外增加多个 `FP`，最多只把该条款算成一个正例条款。

这对合同审查系统不够，因为业务更关心的是：

- 该条款里具体漏了哪些风险点
- 该条款里是否多报了不成立的风险点
- 风险点与修改建议是否逐项对应

### 1.4 当前解释/建议分容易被“空文本”和“照抄文本”抬高

当前解释与建议评分位于 [judge.py](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/src/contract_metrics/judge.py)。

存在两个明显问题：

1. 当标签建议与预测建议同时为 `无` 时，`text_similarity("无", "无") = 1.0`
2. 若预测建议与标签建议完全相同，会直接得到 `content_accuracy = 1.0`

本次抽样中已经看到多组：

- `LABEL_SUG: 无`
- `PRED_SUG: 无`
- `content_accuracy = 1.0`

这会导致：

- “没有给建议”被错误地视作“建议完全正确”
- 如果标签文本本来就是从第三方结果转写来的，那么第三方建议天然高分

因此当前的建议准确率不适合作为核心指标。

### 1.5 对齐误差仍然很大，说明当前分数还有匹配噪声

最新报告里的告警：

- `1-品牌球馆冠名合作协议: 2 label entries unmatched to clauses`
- `1-品牌球馆冠名合作协议/third_party: 14 predictions unmatched`
- `2-服务协议: 5 label entries unmatched to clauses`
- `2-服务协议/third_party: 14 predictions unmatched`
- `2-服务协议/final_applied: 2 predictions unmatched`
- `3-保密协议: 2 label entries unmatched to clauses`
- `3-保密协议/third_party: 11 predictions unmatched`

这说明：

- 当前 clause alignment 还没有稳定到足以作为最终评测底座
- 识别指标中仍混入了“对不齐”带来的系统误差

## 2. 目前哪些指标还能保留

下面这些可以保留，但要降级为“辅助指标”：

- 条款级 `Recall / Miss Rate`
  - 适合做第一层粗筛，判断模型是否能先把有风险的条款挑出来
- 条款级 `Precision / False Positive Rate`
  - 适合判断模型是否过度报风险
- `policy_a / policy_b`
  - 仍可保留，但建议改名为“采纳口径”和“覆盖口径”

不建议继续把下面这些当成主指标：

- 当前规则版 `Explanation Accuracy`
- 当前规则版 `Suggestion Accuracy`
- 当前 `third_party vs label` 的内容质量对比结果

## 3. 更适合合同审查系统的评估方案

建议把评估拆成 4 层，而不是只做一个条款级总表。

### 3.1 第一层：风险条款筛查能力

评测单位：条款。

目标：判断模型能否先把“值得进一步审查的条款”筛出来。

建议指标：

- `Clause Recall = 命中风险条款数 / 标签风险条款数`
- `Clause Precision = 命中风险条款数 / 模型判定风险条款数`
- `Clause F1`
- `Critical Clause Recall`
  - 对高优先级风险条款单独统计召回率

为什么需要这一层：

- 这层最接近真实工作流中的“先筛查，再深审”
- 也最适合做速度与效果平衡

### 3.2 第二层：风险点枚举能力

评测单位：风险点，而不是条款。

这是当前最缺的一层。

建议标签结构最少包含：

- `contract_id`
- `clause_id`
- `risk_id`
- `risk_type`
- `risk_title`
- `risk_reason`
- `risk_consequence`
- `adoption_status`

建议指标：

- `Risk Recall = 匹配到的标签风险点 / 标签风险点总数`
- `Risk Precision = 匹配到的模型风险点 / 模型风险点总数`
- `Risk F1`
- `Over-detection Rate = 未匹配预测风险点 / 模型风险点总数`

匹配原则建议：

- 先在同一 `clause_id` 内匹配
- 再做风险点级一对一匹配
- 允许一个条款内存在多个风险点

这样才能真正回答：

- 模型是不是只看到了“有风险”
- 还是确实把这个条款中的 2 到 3 个风险点都找全了

### 3.3 第三层：风险解释质量

评测单位：已匹配成功的风险点。

不建议继续用单纯字符串相似度做主评分，建议采用“结构化字段 + LLM 裁判”双轨制。

建议字段：

- `risk_type`
- `reason`
- `consequence`
- `evidence_span`

建议指标：

- `Type Accuracy`
  - 风险类型是否一致
- `Reason Alignment`
  - 风险原因是否一致
- `Consequence Completeness`
  - 是否说明了对乙方/委托方的不利后果
- `Evidence Grounding`
  - 是否引用或绑定到了正确条款

建议打分方式：

- 基础版：规则校验字段是否为空、是否绑定原文
- 进阶版：本地 LLM 裁判输出 0 到 1 分

### 3.4 第四层：修改建议质量

评测单位：已匹配成功的风险点。

建议把“建议质量”拆成 4 个维度：

- `Direction Correctness`
  - 修改方向是否正确
- `Edit Coverage`
  - 是否覆盖标签中的关键修改点
- `Actionability`
  - 是否可直接执行，避免空泛建议
- `Legal Safety`
  - 是否引入新的明显法律风险

如果后续能拿到“最终采用版本”的结构化修订点，还可以增加：

- `Adoption-weighted Suggestion Score`
  - 采纳项权重高于未采纳项

## 4. 建议如何使用现有三类材料

你现在手里有三类材料：

- Alpha GPT 审查结果
- 最终审查意见
- 采纳情况说明

建议角色重新定义如下：

- `采纳情况说明`
  - 用来构建 gold label
- `third_party / Alpha GPT`
  - 用作 baseline competitor
- `最终审查意见`
  - 用作辅助参考，不直接当 gold

原因：

- `third_party` 现在与标签高度同源，不能再兼任基准和标签
- `final_applied` 本身更像业务产物，不一定是结构化风险输出

## 5. 预处理与上下文组织建议

你提到现在像是在“一句话一句话地审查”，这不适合合同审查 agent 的最终形态。

建议未来推理单位采用“条款块”而不是“句子块”。

### 5.1 推荐最小上下文单元

推荐输入单元：

- 当前条款全文
- 上一条款标题或正文摘要
- 下一条款标题或正文摘要
- 所属章节标题
- 合同基本信息摘要

建议每个预测结果都强制输出：

- `clause_id`
- `risk_type`
- `risk_title`
- `reason`
- `consequence`
- `suggestion`
- `evidence_span`

### 5.2 为什么不要做纯句子级审查

纯句子级会带来：

- 定义项、例外条款、违约责任跨句关联被切断
- 上下位条款关系丢失
- 召回率变差
- 推理调用次数大幅上升，速度更慢

### 5.3 更合理的工程方案

建议采用两阶段：

1. 条款筛查
   - 用轻量模型或规则先判断该条款是否值得深审
2. 风险抽取
   - 只对疑似风险条款做结构化风险点抽取和建议生成

这样既保留上下文，又能控制推理成本。

## 6. 下一版指标建议

建议下一版报告最少保留这 8 个核心指标：

1. `Clause Recall`
2. `Clause Precision`
3. `Clause F1`
4. `Risk Recall`
5. `Risk Precision`
6. `Risk F1`
7. `Explanation Score`
8. `Suggestion Score`

其中：

- 第一组衡量“能否先筛出来”
- 第二组衡量“风险点找得全不全、准不准”
- 第三四组衡量“审查意见写得是否像专业审查”

另建议增加 3 个辅助指标：

1. `Critical Risk Recall`
2. `Adoption-weighted Recall`
3. `Average Clauses Reviewed per Contract`

第三项能帮助你平衡：

- 审得更细
- 还是跑得更快

## 7. 对当前结果的最终判断

对这份 [evaluation_report.md](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/20260317_word2md_eval/evaluation_report.md) 的判断是：

- 当前异常分数不主要是公式算错
- 主要是标签设计、评分粒度、以及同源对比方式有问题
- 目前结果可以作为“解析链路联调结果”，不能作为“模型能力排行榜”

如果接下来进入指标重构，优先级建议是：

1. 先把 gold label 从 `third_party` 文本依赖中剥离出来
2. 再把评测单位从“条款级是否有风险”升级到“风险点级一对一匹配”
3. 最后再引入解释与建议质量评分
