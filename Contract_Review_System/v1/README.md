# Contract Review System v1

v1 目标：先建立可复现的对比评测体系，在不使用其它合同作为参考的前提下，比较三类输出：

1. 第三方平台
2. 他们的最终应用版
3. 本地 LLM prompt-only（本系统 v1）

---

## 项目文件结构

```
v1/
├── README.md                         # 本文档
├── requirements.txt                  # Python 依赖
├── pyrightconfig.json                # Pyright 类型检查配置
│
├── src/
│   └── contract_review_v1/
│       ├── __init__.py
│       ├── schema.py       # 数据集加载与结构化对象（ClauseEvaluationRecord、ParsedReview）
│       ├── runner.py       # 本地 LLM 调用与输出解析（generate_system_review）
│       ├── metrics.py      # 三类指标计算（evaluate_participant、_explanation_score 等）
│       └── reporting.py    # Markdown + JSON 报告渲染（render_markdown_report）
│
├── scripts/
│   ├── prepare_real_dataset.py   # 将真实合同目录转换为评测 JSON 数据集
│   ├── run_eval.py               # 纯评测入口（对比三方结果，不会执行正式审查）
│   └── run_formal_review.py      # 正式审查入口（调用 LLM + 自动评测，输出 runN 目录）
│
├── data/
│   ├── sample_eval_dataset.json       # 样例数据（少量条款，用于快速验证流程）
│   ├── real_eval_dataset.json         # 真实合同评测数据集（启发式筛选版）
│   ├── real_eval_dataset_run3.json    # 早期 run 使用的数据集（少量条款模式）
│   └── real_eval_dataset_full.json    # 真实合同评测数据集（全量段落模式，run3 使用）
│
└── outputs/
    ├── real/                  # 仅跑 run_eval.py 时的输出
    └── formal_runs/
        └── runN/              # run_formal_review.py 每次自动创建
            ├── review_report.md       # 与 contract_review_agent.py 同风格的审查报告
            ├── evaluation_metrics.md  # 三方对比评测报告（Markdown）
            ├── evaluation_metrics.json
            └── run_meta.json          # 本次运行参数与文件清单
```

---

## 数据集格式

每条 clause 至少包含：

| 字段 | 说明 |
|---|---|
| `contract_id` | 合同 ID，如 `1-品牌球馆冠名合作协议` |
| `clause_id` | 条款 ID，如 `1-品牌球馆冠名合作协议_c001` |
| `clause_text` | 原始条款文本 |
| `ground_truth` | 人工最终采纳版（真值），来自"采纳情况说明"文档 |
| `third_party` | 第三方平台输出，来自"审查意见书"文档 |
| `final_applied` | 最终应用版输出，来自"最终审查意见"文档 |
| `explanation_keywords` | 评判解释准确率时的关键词列表（从 `ground_truth` 提取） |
| `suggestion_keywords` | 评判修改建议准确率时的关键词列表 |

每个 `ParsedReview` 字段包含：

```json
{
  "has_risk": true,
  "risk_level": null,
  "risk_points": ["关键词1", "关键词2"],
  "explanation": "风险解释文本",
  "suggestion": "修改建议文本",
  "raw_text": "原始输出全文"
}
```

---

## 指标定义与计算公式

### 指标一：风险点识别

以 `has_risk` 字段与 `ground_truth.has_risk` 比较，计算混淆矩阵：

```
准确率 = (TP + TN) / (TP + TN + FP + FN)
漏报率 = FN / (TP + FN)        # ground_truth 有风险但未识别
误报率 = FP / (FP + TN)        # ground_truth 无风险但误报
```

### 指标二：风险解释准确率

**评分函数**（`_explanation_score`）：

- 若 `ground_truth.has_risk == False`：预测无风险得 1.0，预测有风险得 0.0
- 若 `ground_truth.has_risk == True`：

```
score = hits / len(explanation_keywords)
      = 在 prediction.explanation 中命中的关键词数 / 总期望关键词数
```

关键词匹配采用去空格子串匹配（大小写不敏感）。**正确阈值 ≥ 0.80**。

**平均分**：所有条款得分之和 / 条款总数。

### 指标三：修改建议准确率

**评分函数**（`_suggestion_score`）：

- 若 `ground_truth.has_risk == False`：同上
- 若 `ground_truth.has_risk == True`：

```
coverage     = 在 prediction.suggestion 中命中的 suggestion_keywords 比例
actionability = 1.0（若建议文本含"建议/应/修改/补充/删除/明确/替换"之一），否则 0.0

score = 0.7 * coverage + 0.3 * actionability
```

**正确阈值 ≥ 0.75**。

---

## ⚠️ 当前评测的已知局限：数据对齐偏差

现有数据集通过 **按段落索引对齐** 将原合同与各审查文档对应：即原合同第 i 段 ↔ 各审查文档第 i 段。

但各文档结构差异显著：

| 文档 | 结构 |
|---|---|
| 原合同 | 条款式：标题、当事人、正文各条 |
| 第三方审查意见书 | 审查风格，行文与原合同相近（标题对应标题，条款对应条款） |
| 最终审查意见 | 编号列表式（1. 双方确立…），与原合同段落位置无对应关系 |
| 采纳情况说明（ground_truth） | 也是编号列表式，与最终审查意见结构不同 |

**导致的现象：**

- **第三方平台**得分较高（75%）：其文档结构与 ground_truth 近似，段落索引对齐后内容也较接近
- **最终应用版**得分较低（49%）：其文档是逐条列举的修改意见，第 i 条并不对应原合同第 i 段，造成大量语义错位
- **本系统 v1**得分最低（12%）：prompt-only 模型本身能力有限，且存在同样的对齐问题

**重要结论：指标二、三的绝对数值不能直接比较三方质量高低，当前评测的价值在于调试流程。**

**v1 已在 `prepare_real_dataset.py` 中将对齐方式升级为"反向语义对齐"**（`alignment_method: semantic_reverse`）：对每条审查文档段落，通过关键词评分反向找到它最可能讨论的合同条款，再聚合。详见下方原理说明。进一步提升可在 v2 中引入向量 embedding 替换关键词打分。

## 运行

Windows + conda 环境示例：

```powershell
conda activate langchain
cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v1
python scripts/run_eval.py --dataset data/sample_eval_dataset.json --output-dir outputs
```

如果暂时只想验证评测流程，不调用本地模型：

```powershell
python scripts/run_eval.py --dataset data/sample_eval_dataset.json --output-dir outputs --skip-system
```

执行后会生成：

- outputs/evaluation_report.md
- outputs/evaluation_detail.json

## 真实合同数据转换

如果你的真实合同目录为 `data/合同数据-2026.3.12`，可先自动转换为评测 JSON：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/prepare_real_dataset.py --input-root data/合同数据-2026.3.12 --output Contract_Review_System/v1/data/real_eval_dataset.json
```

如果担心启发式筛选遗漏信息，可使用全量条款模式：

```powershell
python Contract_Review_System/v1/scripts/prepare_real_dataset.py --input-root data/合同数据-2026.3.12 --output Contract_Review_System/v1/data/real_eval_dataset.json --keep-all-clauses
```

生成后的数据中会包含 `conversion_trace`，记录候选条款数、入选条款数和被过滤条款预览。

然后运行评测：

```powershell
python Contract_Review_System/v1/scripts/run_eval.py --dataset Contract_Review_System/v1/data/real_eval_dataset.json --output-dir Contract_Review_System/v1/outputs/real
```

如需先验证流程不调用模型：

```powershell
python Contract_Review_System/v1/scripts/run_eval.py --dataset Contract_Review_System/v1/data/real_eval_dataset.json --output-dir Contract_Review_System/v1/outputs/real --skip-system
```

## 正式审查运行（run1/run2 输出）

如果你要用“1-品牌球馆冠名合作协议”做测试，使用“2-服务协议”和“3-保密协议”做知识库，可运行：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_formal_review.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --knowledge-prefixes 2- 3- --output-root Contract_Review_System/v1/outputs/formal_runs
```

每次运行会自动新建 `run1`、`run2`... 目录，并输出：

- `review_report.md`：与 `contract_review_agent.py` 同风格的详细审查报告
- `run_meta.json`：本次运行参数、模型、输入输出文件清单

## 下一步

v1 跑通后，建议按留一法扩展三份合同数据；v2 再引入知识库检索，保持同一评测口径对比增益。
