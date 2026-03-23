# Contract Metrics V2 Evaluation Report

## 概览

- 数据集: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\metrics_v2\local_llm\outputs_fix2\20260317_word2md_eval_third_party_fix2_20260318\dataset_with_local_llm.json`
- 参与方: third_party, final_applied, local_llm
- 合同数量: 3
- 条款对齐阈值: 0.33
- 风险点匹配阈值: 0.45
- 告警数: 26

> 说明：v2 刻意弱化了“文本完全一致就高分”的旧逻辑，更强调条款筛查、风险点枚举和建议是否可执行。

## 口径A（采纳 + 部分采纳）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 58.33% | 38.89% | 46.67% | 14.29% | 11.11% | 12.50% | 2 | 17 | 21 | 75.00% | 25.00% | 0.00% | 0.00% |
| local_llm | 61.54% | 44.44% | 51.61% | 35.71% | 27.78% | 31.25% | 5 | 19 | 21 | 100.00% | 100.00% | 0.00% | 0.00% |
| third_party | 62.07% | 100.00% | 76.60% | 51.43% | 100.00% | 67.92% | 18 | 55 | 21 | 94.44% | 80.56% | 27.78% | 22.22% |

## 口径B（采纳说明全部意见）

| Participant | Clause P | Clause R | Clause F1 | Risk P | Risk R | Risk F1 | Matched | Pred Risks | Gold Risks | Explanation Structure | Suggestion Actionability | Exact Title Overlap | Exact Suggestion Overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| final_applied | 75.00% | 31.03% | 43.90% | 14.29% | 6.06% | 8.51% | 2 | 17 | 40 | 75.00% | 25.00% | 0.00% | 0.00% |
| local_llm | 84.62% | 37.93% | 52.38% | 64.29% | 27.27% | 38.30% | 9 | 19 | 40 | 97.22% | 100.00% | 0.00% | 0.00% |
| third_party | 100.00% | 100.00% | 100.00% | 91.43% | 96.97% | 94.12% | 32 | 55 | 40 | 92.19% | 81.25% | 40.62% | 28.12% |

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
- 3-保密协议/final_applied: 2 predicted risks unmatched
- 3-保密协议/final_applied: 2 predicted risks unmatched
- 3-保密协议/local_llm: 1 predicted risks unmatched
- 3-保密协议/local_llm: 1 predicted risks unmatched
