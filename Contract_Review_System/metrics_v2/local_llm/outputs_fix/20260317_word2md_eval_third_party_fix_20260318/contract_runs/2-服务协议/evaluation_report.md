# Contract Metrics V2 Evaluation Report

## 概览

- 数据集: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\metrics_v2\local_llm\outputs_fix\20260317_word2md_eval_third_party_fix_20260318\contract_runs\2-服务协议\dataset_with_local_llm.json`
- 参与方: third_party, final_applied, local_llm
- 合同数量: 1
- 条款对齐阈值: 0.33
- 风险点匹配阈值: 0.45
- 告警数: 12

> 说明：v2 刻意弱化了“文本完全一致就高分”的旧逻辑，更强调条款筛查、风险点枚举和建议是否可执行。

## 当前合同

- 合同 ID: `2-服务协议`
- 原合同 Markdown: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v2\word2md\outputs_md\20260317_word2md_eval\2-服务协议\1-原合同-服务协议\output.md`
- 原合同源文件: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\data\合同数据-2026.3.12\2-服务协议\1-原合同-服务协议.docx`
- 采纳说明 Markdown: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v2\word2md\outputs_md\20260317_word2md_eval\2-服务协议\4-采纳情况说明-服务协议\output.md`

## 口径A（采纳 + 部分采纳）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 100.00% | 100.00% | 100.00% | 20.00% | 25.00% | 22.22% | 1 | 6 | 6 | 75.00% | 25.00% | 0.00% | 0.00% |
| local_llm | 66.67% | 50.00% | 57.14% | 50.00% | 50.00% | 50.00% | 2 | 6 | 6 | 100.00% | 100.00% | 0.00% | 0.00% |
| third_party | 50.00% | 100.00% | 66.67% | 30.77% | 100.00% | 47.06% | 4 | 24 | 6 | 87.50% | 62.50% | 50.00% | 100.00% |

## 口径B（采纳说明全部意见）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 100.00% | 50.00% | 66.67% | 20.00% | 10.00% | 13.33% | 1 | 6 | 14 | 75.00% | 25.00% | 0.00% | 0.00% |
| local_llm | 100.00% | 37.50% | 54.55% | 75.00% | 30.00% | 42.86% | 3 | 6 | 14 | 100.00% | 100.00% | 0.00% | 0.00% |
| third_party | 100.00% | 100.00% | 100.00% | 76.92% | 100.00% | 86.96% | 10 | 24 | 14 | 80.00% | 75.00% | 60.00% | 90.00% |

## 使用提醒

- `Exact Title Overlap` 或 `Exact Suggestion Overlap` 很高时，说明该参与方与标签可能存在同源文本风险。
- `Suggestion Actionability` 低并不一定表示方向错误，也可能只是没有给出具体可执行建议。
- 当前结果适合作为联调和直觉验证，不适合作为严格能力排行榜。

## 告警

- 2-服务协议: 2 gold risks unmatched
- 2-服务协议/third_party: 11 predicted risks unmatched
- 2-服务协议: 4 gold risks unmatched
- 2-服务协议/third_party: 11 predicted risks unmatched
- 2-服务协议: 2 gold risks unmatched
- 2-服务协议/final_applied: 1 predicted risks unmatched
- 2-服务协议: 4 gold risks unmatched
- 2-服务协议/final_applied: 1 predicted risks unmatched
- 2-服务协议: 2 gold risks unmatched
- 2-服务协议/local_llm: 2 predicted risks unmatched
- 2-服务协议: 4 gold risks unmatched
- 2-服务协议/local_llm: 2 predicted risks unmatched
