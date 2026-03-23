# Contract Metrics V2 Evaluation Report

## 概览

- 数据集: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\metrics_v2\local_llm\outputs_fix\20260317_word2md_eval_third_party_fix_20260318\contract_runs\3-保密协议\dataset_with_local_llm.json`
- 参与方: third_party, final_applied, local_llm
- 合同数量: 1
- 条款对齐阈值: 0.33
- 风险点匹配阈值: 0.45
- 告警数: 4

> 说明：v2 刻意弱化了“文本完全一致就高分”的旧逻辑，更强调条款筛查、风险点枚举和建议是否可执行。

## 当前合同

- 合同 ID: `3-保密协议`
- 原合同 Markdown: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v2\word2md\outputs_md\20260317_word2md_eval\3-保密协议\1-原合同-保密协议\output.md`
- 原合同源文件: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\data\合同数据-2026.3.12\3-保密协议\1-原合同-保密协议.doc`
- 采纳说明 Markdown: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v2\word2md\outputs_md\20260317_word2md_eval\3-保密协议\4-采纳情况说明-关于《保密协议》的审查意见书\output.md`

## 口径A（采纳 + 部分采纳）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0 | 2 | 3 | 0.00% | 0.00% | 0.00% | 0.00% |
| local_llm | 25.00% | 33.33% | 28.57% | 0.00% | 0.00% | 0.00% | 0 | 5 | 3 | 0.00% | 0.00% | 0.00% | 0.00% |
| third_party | 60.00% | 100.00% | 75.00% | 50.00% | 100.00% | 66.67% | 3 | 6 | 3 | 100.00% | 91.67% | 100.00% | 0.00% |

## 口径B（采纳说明全部意见）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0 | 2 | 6 | 0.00% | 0.00% | 0.00% | 0.00% |
| local_llm | 50.00% | 40.00% | 44.44% | 50.00% | 33.33% | 40.00% | 2 | 5 | 6 | 87.50% | 100.00% | 0.00% | 0.00% |
| third_party | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 6 | 6 | 6 | 100.00% | 91.67% | 100.00% | 0.00% |

## 使用提醒

- `Exact Title Overlap` 或 `Exact Suggestion Overlap` 很高时，说明该参与方与标签可能存在同源文本风险。
- `Suggestion Actionability` 低并不一定表示方向错误，也可能只是没有给出具体可执行建议。
- 当前结果适合作为联调和直觉验证，不适合作为严格能力排行榜。

## 告警

- 3-保密协议/final_applied: 2 predicted risks unmatched
- 3-保密协议/final_applied: 2 predicted risks unmatched
- 3-保密协议/local_llm: 1 predicted risks unmatched
- 3-保密协议/local_llm: 1 predicted risks unmatched
