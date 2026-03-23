# Contract Metrics V2 Evaluation Report

## 概览

- 数据集: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\metrics_v2\local_llm\outputs_fix\20260317_word2md_eval_third_party_fix_20260318\contract_runs\1-品牌球馆冠名合作协议\dataset_with_local_llm.json`
- 参与方: third_party, final_applied, local_llm
- 合同数量: 1
- 条款对齐阈值: 0.33
- 风险点匹配阈值: 0.45
- 告警数: 10

> 说明：v2 刻意弱化了“文本完全一致就高分”的旧逻辑，更强调条款筛查、风险点枚举和建议是否可执行。

## 当前合同

- 合同 ID: `1-品牌球馆冠名合作协议`
- 原合同 Markdown: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v2\word2md\outputs_md\20260317_word2md_eval\1-品牌球馆冠名合作协议\1-原合同：品牌球馆冠名合作协议\output.md`
- 原合同源文件: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\data\合同数据-2026.3.12\1-品牌球馆冠名合作协议\1-原合同：品牌球馆冠名合作协议.docx`
- 采纳说明 Markdown: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v2\word2md\outputs_md\20260317_word2md_eval\1-品牌球馆冠名合作协议\4-采纳情况说明-品牌球馆冠名合作协议\output.md`

## 口径A（采纳 + 部分采纳）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 37.50% | 27.27% | 31.58% | 11.11% | 9.09% | 10.00% | 1 | 9 | 12 | 75.00% | 25.00% | 0.00% | 0.00% |
| local_llm | 83.33% | 45.45% | 58.82% | 50.00% | 27.27% | 35.29% | 3 | 8 | 12 | 100.00% | 100.00% | 0.00% | 0.00% |
| third_party | 68.75% | 100.00% | 81.48% | 68.75% | 100.00% | 81.48% | 11 | 25 | 12 | 95.45% | 84.09% | 0.00% | 0.00% |

## 口径B（采纳说明全部意见）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 62.50% | 31.25% | 41.67% | 11.11% | 5.88% | 7.69% | 1 | 9 | 20 | 75.00% | 25.00% | 0.00% | 0.00% |
| local_llm | 100.00% | 37.50% | 54.55% | 66.67% | 23.53% | 34.78% | 4 | 8 | 20 | 100.00% | 100.00% | 0.00% | 0.00% |
| third_party | 100.00% | 100.00% | 100.00% | 100.00% | 94.12% | 96.97% | 16 | 25 | 20 | 96.88% | 81.25% | 6.25% | 0.00% |

## 使用提醒

- `Exact Title Overlap` 或 `Exact Suggestion Overlap` 很高时，说明该参与方与标签可能存在同源文本风险。
- `Suggestion Actionability` 低并不一定表示方向错误，也可能只是没有给出具体可执行建议。
- 当前结果适合作为联调和直觉验证，不适合作为严格能力排行榜。

## 告警

- 1-品牌球馆冠名合作协议: 1 gold risks unmatched
- 1-品牌球馆冠名合作协议/third_party: 9 predicted risks unmatched
- 1-品牌球馆冠名合作协议: 3 gold risks unmatched
- 1-品牌球馆冠名合作协议/third_party: 9 predicted risks unmatched
- 1-品牌球馆冠名合作协议: 1 gold risks unmatched
- 1-品牌球馆冠名合作协议: 3 gold risks unmatched
- 1-品牌球馆冠名合作协议: 1 gold risks unmatched
- 1-品牌球馆冠名合作协议/local_llm: 2 predicted risks unmatched
- 1-品牌球馆冠名合作协议: 3 gold risks unmatched
- 1-品牌球馆冠名合作协议/local_llm: 2 predicted risks unmatched
