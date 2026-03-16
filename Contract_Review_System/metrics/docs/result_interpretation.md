# 结果解读模板

## 0. 先看报告结构（evaluation_report.md）

`evaluation_report.md` 固定分 4 块：

1. `概览`：数据集路径、参与方、LLM 裁判开关、告警数量。
2. `口径A`：采纳+部分采纳为正例。
3. `口径B`：全部意见为正例。
4. `分合同概览` + `解析告警`：按合同查看 TP/FP/TN/FN，并定位解析或匹配问题。

如果只做 prompt-only 能力测试，建议参与方只看：`third_party` 与 `agent`。

## 1. 先看哪张表

先看 `口径A`，再看 `口径B`。

- 口径A更贴近“最终会被采纳”的业务目标。
- 口径B更贴近“模型是否能提出足够多风险意见”。

## 2. 如何判断是否优于第三方

对比 `agent` 与 `third_party`：

- 风险识别：
  - `Risk Accuracy` 越高越好
  - `Miss Rate` 越低越好（漏报少）
  - `False Positive Rate` 越低越好（误报少）
- 风险解释（仅 TP 上评分）：
  - `Explanation Direction` 越高越好
  - `Explanation Accuracy` 越高越好
  - `Explanation Completeness` 越高越好
- 修改建议（仅 TP 上评分）：
  - `Suggestion Direction` 越高越好
  - `Suggestion Accuracy` 越高越好
  - `Suggestion Completeness` 越高越好

## 3. 双口径差异怎么读

- A 高、B 低：模型更接近“最终采纳偏好”，但覆盖面不够。
- A/B 都高：覆盖和采纳一致性都不错。
- A 低、B 高：模型提了很多意见，但与真实采纳偏好偏离。

## 4. 分合同表怎么读（TP/FP/TN/FN）

每行代表一个参与方在一个合同、一个口径下的识别统计：

- `TP`：标签有风险，模型也识别为风险。
- `FP`：标签无风险，模型识别为风险（误报）。
- `TN`：标签无风险，模型也未识别（正确排除）。
- `FN`：标签有风险，模型未识别（漏报）。

优先定位 `FN` 和 `FP` 高的合同，再看告警中的 unmatched 原因。

## 5. 解析告警怎么用

`解析告警` 常见三类：

- `conversion failed`：源文件转 md 失败，导致该参与方信息不完整。
- `label entries unmatched to clauses`：标签条款没成功映射到合同条款。
- `<participant> predictions unmatched`：该参与方输出缺少可匹配条款引用。

告警多时，先修数据/解析，再比较模型优劣，否则结论会被噪声影响。

## 6. Prompt-Only 阶段建议

当前阶段建议命令：

```powershell
python Contract_Review_System/metrics/scripts/evaluate.py \
  --dataset Contract_Review_System/metrics/outputs/datasets/dataset_20260316_105814.json \
  --agent-md Contract_Review_System/v1/outputs/ablation_runs/prompt-only/<run_id>/review_report.md \
  --participants third_party,agent
```

这样可以避免把知识库检索能力混入当前实验结论。

## 7. 运行留痕

每次运行保留：

- `evaluation_payload.json`
- `evaluation_result.json`
- `evaluation_report.md`
- `evaluation_metrics.csv`
- `README_summary.md`

可确保“输入-参数-结果”全链路可回溯。
