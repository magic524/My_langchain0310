# 合同审查指标与计算公式

本文档给出三个主要评价维度的数学公式与计算流程：

- 指标一：风险点识别 —— 准确率、漏报率、误报率
- 指标二：风险点解释准确率
- 指标三：修改建议（修改版）准确率

**一、符号与基本定义**

- $\mathrm{TP}$：真正例（ground truth 有风险，模型也判断为有风险）
- $\mathrm{FN}$：漏报（ground truth 有风险，模型判断为无风险）
- $\mathrm{FP}$：误报（ground truth 无风险，模型判断为有风险）
- $\mathrm{TN}$：真反例（ground truth 无风险，模型也判断为无风险）
- $N$：样本总数，$N=\mathrm{TP}+\mathrm{FP}+\mathrm{TN}+\mathrm{FN}$

所有比率均按每条条款（clause）统计后聚合。

**二、指标一：风险点识别（识别二分类）**

- 准确率（Accuracy）：

$$
\text{Accuracy} = \frac{\mathrm{TP}+\mathrm{TN}}{\mathrm{TP}+\mathrm{TN}+\mathrm{FP}+\mathrm{FN}} = \frac{\mathrm{TP}+\mathrm{TN}}{N}
$$

含义：模型对条款是否存在风险的总体判断正确比例。

- 漏报率（Miss Rate，也称为召回的反面，False Negative Rate）：

$$
\text{Miss Rate} = \frac{\mathrm{FN}}{\mathrm{TP}+\mathrm{FN}}
$$

含义：在所有实际有风险的条款中，被模型漏判为无风险的比例。计算时分母为所有正例（ground truth 有风险）。

- 误报率（False Positive Rate）：

$$
\text{False Positive Rate} = \frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}
$$

含义：在所有实际无风险的条款中，被模型误判为有风险的比例。计算时分母为所有负例（ground truth 无风险）。

计算流程（步骤）：
1. 读入数据集，逐条比较 `ground_truth.has_risk` 与 `prediction.has_risk`。
2. 累加四类计数：TP/FP/TN/FN。
3. 按上面公式计算三个指标（若某分母为 0 则定义比率为 0，避免除零）。

**三、指标二：风险点解释准确率（Explanation Accuracy）**

单条条款的解释得分（per-clause explanation score）按如下规则计算：

1. 若 ground truth 标注为无风险（$\mathrm{has\_risk}=\text{False}$）：
   - 若模型也判断为无风险，则该条得分为 $1$；否则得分为 $0$。

2. 若 ground truth 标注为有风险：
   - 首先确定“期望关键词集合” $K$：如果 `explanation_keywords` 非空则取之，否则使用 `ground_truth.risk_points`。
   - 计算覆盖率（keyword coverage）：

$$
\text{Coverage} = \frac{\#\{k\in K:\;k\text{ 在预测解释中被匹配}\}}{|K|}
$$

   - 单条得分即为 Coverage（若 $K$ 为空则定义为 0）。

聚合方式（总体解释准确率）：对所有条款的单条得分取算术平均：

$$
\text{ExplanationAccuracy} = \frac{1}{N}\sum_{i=1}^{N} s_i
$$

其中 $s_i$ 为第 $i$ 条的解释得分。

注意：文中实现中关键词匹配为“忽略空白并不区分大小写的子串匹配”（即先去空白再检查关键词是否为预测文本的子串）。因此实际命中按该规则计算。

计算流程（步骤）：
1. 对每条记录：若 ground truth 无风险，则按规则赋分 1 或 0。
2. 否则构造关键词集合 $K$（优先 `explanation_keywords`，否则 `ground_truth.risk_points`）。
3. 对每个关键词按去空白、小写后是否为预测解释文本的子串判断命中数，计算 Coverage。
4. 把所有条目的 Coverage（或 0/1）平均为总体解释准确率。

示例公式（若仅对有风险子集求平均，也可按需求改为在正例上求均值）：

$$
\text{ExplanationAccuracy}_{\text{avg}} = \frac{1}{N}\sum_{i=1}^{N} \mathrm{coverage}_i
$$

**四、指标三：修改建议（Suggestion / 修改版）准确率**

单条条款的修改建议得分由两部分组成：关键词覆盖率（Coverage）与可操作性（Actionability）。具体实现为：

- 关键词覆盖率：

$$
\text{Coverage}_{\text{sug}} = \frac{\#\{k\in S:\;k\text{ 在预测建议中被匹配}\}}{|S|}
$$

其中 $S$ 为 `suggestion_keywords`（若空则 Coverage 定义为 0）。

- 可操作性（Actionability）：使用规则词列表（例如实现中为："建议", "应", "修改", "补充", "删除", "明确", "替换"）检查预测建议文本是否包含任一动作型标记：若包含，则

$$
\text{Actionability} = 1,\quad\text{否则}=0
$$

- 单条最终得分：

$$
s_{\text{sug}} = 0.7\times\text{Coverage}_{\text{sug}} + 0.3\times\text{Actionability}
$$

聚合为所有条款得分的平均值：

$$
\text{SuggestionAccuracy} = \frac{1}{N}\sum_{i=1}^{N} s_{\text{sug},i}
$$

计算流程（步骤）：
1. 对每条记录构造 `suggestion_keywords`（若无则 Coverage=0）。
2. 计算关键词覆盖率与是否含动作标记（Actionability）。
3. 按加权公式计算单条得分（0.7/0.3 权重）。
4. 对所有条款取平均作为总体修改建议准确率。

**五、示例：如何选择正确/错误示例（用于报告展示）**

实现中存在示例挑选逻辑：

- 对于解释维度，使用阈值 $T_{exp}=0.8$；对于修改建议维度，使用阈值 $T_{sug}=0.75$。
- 遍历所有条款并计算每条的得分 $s$：
  - 第一个满足 $s\ge T$ 的条款作为“正确示例”；第一个满足 $s<T$ 的作为“错误示例”。
- 同时计算这些维度上的平均得分以作为维度分数显示。

**六、实现注意事项与边界处理**

- 所有比率分母为 0 时，建议返回 0.0（实现中使用了 `_safe_div` 做防护）。
- 关键词集合若为空，应明确业务语义（当前实现中对解释关键词为空会回退到 `ground_truth.risk_points`；若仍空则返回 0）。
- 聚合方式可按业务需求改为仅在正例上计算（例如解释准确率只对 ground truth 有风险的条款求均值），请在计算前确定该策略。

---

**七、数据来源与 ground_truth 说明（项目内实现要点）**

- ground_truth 来源：每个合同目录下的 `4-采纳情况说明-*.docx`（脚本中称为 `adoption_file`），由人工最终采纳/确认的审查意见构成，作为本项目的参考真值。

- 如何从原始文件构造 ground_truth：
   1. 脚本 `Contract_Review_System/v1/scripts/prepare_real_dataset.py` 读取合同目录下的 Word 文件（`1-原合同*`、`2-第三方平台审查结果`、`3-最终审查意见*`、`4-采纳情况说明*`）。
   2. 使用 `examples/Docs-by-LangChain/contract_review_agent.py` 中的 `parse_word_file` 提取段落、批注和修订痕迹。
   3. 脚本对 `4-采纳情况说明`（采纳说明）、第三方结果和最终审查意见分别做段落级解析，然后通过“语义反向对齐”（把审查段落反向分配给最相关的合同条款）得到每条条款对应的审查片段。
   4. 对分配到某条款的采纳说明片段，调用 `structured_review_from_snippet`（在脚本中）以规则与 `parse_review_text` 的解析结果构造 `ground_truth`：
       - 若片段包含结构化字段（如“风险级别”、“问题说明”、“建议修改”）或明确标注为“无需批注”，则按解析结果填充 `ParsedReview`。
       - 否则使用关键词/标记启发式判断（检测风险相关词、建议性词汇、截取前若干字符作为 explanation/suggestion），若无实质内容则标记为无风险。

- 对齐与相似性：反向对齐基于 `build_knowledge_documents`（把段落、批注、修订等转为检索文档）和 `score_document`（按词重叠、短语匹配与文档类型加权）来决定每个审查段落与哪个合同条款最相关。

- 因此测量流程总体为：
   1. 准备阶段：从 Word 文件提取条款与采纳说明段落并对齐到条款。
   2. 结构化：把对齐后的采纳说明片段转为 `ParsedReview` 结构（即项目中的 `ground_truth`）。
   3. 评估阶段：对于模型/第三方预测，也用相同的结构化流程得到 `ParsedReview`，然后按文档前部定义的指标（识别、解释、建议）逐条比较并聚合。

- 实践要点与局限：
   - ground_truth 依赖人工撰写的“采纳说明”，质量受人工写法和模糊表述影响。
   - 反向对齐与打分是基于关键词/短语重叠的启发式方法，可能存在错配或遗漏短片段的风险。
   - 关键词抽取、段落截断等规则会影响解释/建议的覆盖率计算，需要在对外说明中明确这些实现细节。

---

如果需要，我可以把上述要点写成更短的摘要并插入到报告中，或直接把 `real_eval_dataset_full.json` 中的一个合同样例摘出作为示例说明。

如果需要，我可以将此文档转换为项目内的 README 段落，或把公式示例替换为按你的真实数据计算的数值报告。

**八、结果文件与输入文件对应关系（追溯说明）**

- 在本项目的数据准备流程中，每个合同目录通常包含以下文件/目录：
   - `1-原合同*`（原始合同文本）
   - `2-第三方平台审查结果/`（第三方审查输出，按提供商可能有子目录）
   - `3-最终审查意见*`（最终应用版或内部审查意见）
   - `4-采纳情况说明*`（人工采纳/确认的意见，作为 ground_truth）

- 脚本 `Contract_Review_System/v1/scripts/prepare_real_dataset.py` 的选择规则：
   - `original_file`：选取以 `1-原合同` 为前缀的文件。
   - `third_party_file`：在 `2-第三方平台审查结果` 目录中选择非临时文件，优先选择文件名包含“审查意见书”的文件；如果目录下有多个提供商（子目录），脚本会递归查找并按优先级选择单个代表文件。
   - `final_review_file`：选取以 `3-最终审查意见` 为前缀的文件，作为“最终应用版”来源。
   - `adoption_file`（ground_truth）：选取以 `4-采纳情况说明` 为前缀的文件，脚本将其解析并视为人工采纳意见生成 `ground_truth`。

- 在输出的数据集中（例如 `real_eval_dataset_full.json`），每个合同对象包含 `source_files` 字段，精确记录了实际被选中的文件路径，示例结构如下：

```json
{
   "contract_id": "1-品牌球馆冠名合作协议",
   "source_files": {
      "original": ".../1-原合同：品牌球馆冠名合作协议.docx",
      "third_party": ".../2-第三方平台审查结果/Alpha GPT/审查意见书-品牌球馆冠名合作协议.docx",
      "final_applied": ".../3-最终审查意见：品牌球馆冠名合作协议.docx",
      "ground_truth": ".../4-采纳情况说明-品牌球馆冠名合作协议.docx"
   },
   "clauses": [ ... ]
}
```

- 追溯评测结果到输入文件的步骤：
   1. 在评测输出（如 `evaluation_metrics.md`）或生成的数据集中找到对应的 `contract_id`。
   2. 在 `real_eval_dataset_full.json` 的 `contracts` 列表中定位该合同条目，查看其 `source_files`，即可获得原始 Word 文件路径。
   3. 在该合同条目的 `clauses` 列表中查找具体 `clause_id`，字段 `ground_truth.raw_text`、`third_party.raw_text`、`final_applied.raw_text` 包含对齐后的审查片段，可直接对照源文件中的段落或批注进行验证。

- 备注：如果你需要逐合同列出被选择的 `third_party` 文件名或对特定提供商进行对比评估，我可以：
   - 从 `Contract_Review_System/v1/data/real_eval_dataset_full.json` 导出每个合同的 `source_files['third_party']` 列表；或
   - 将某一合同的 `clauses` 中 `*_raw_text` 字段还原为单独示例并写入本档说明中。

---
