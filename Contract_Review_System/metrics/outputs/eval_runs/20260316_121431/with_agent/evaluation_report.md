# Contract Metrics Evaluation Report

## 概览

- 数据集: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\metrics\outputs\datasets\dataset_20260316_105814.json`
- 参与方: third_party, final_applied, agent
- LLM 裁判: 关闭
- 警告数: 11

## 口径A（采纳+部分采纳为正例）

| Participant | Risk Accuracy | Miss Rate | False Positive Rate | Explanation Direction | Explanation Accuracy | Explanation Completeness | Suggestion Direction | Suggestion Accuracy | Suggestion Completeness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| agent | 63.64% | 38.46% | 35.94% | 0.00% | 3.66% | 62.50% | 50.00% | 40.06% | 60.83% |
| final_applied | 46.75% | 30.77% | 57.81% | 0.00% | 0.00% | 8.33% | 55.56% | 0.00% | 7.41% |
| third_party | 71.43% | 0.00% | 34.38% | 84.62% | 15.38% | 48.08% | 84.62% | 84.62% | 69.23% |

## 口径B（全部意见为正例）

| Participant | Risk Accuracy | Miss Rate | False Positive Rate | Explanation Direction | Explanation Accuracy | Explanation Completeness | Suggestion Direction | Suggestion Accuracy | Suggestion Completeness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| agent | 54.55% | 57.14% | 38.78% | 0.00% | 4.66% | 58.33% | 58.33% | 42.77% | 63.70% |
| final_applied | 58.44% | 25.00% | 51.02% | 0.00% | 0.00% | 4.76% | 52.38% | 0.00% | 4.76% |
| third_party | 90.91% | 0.00% | 14.29% | 60.71% | 14.29% | 38.39% | 71.43% | 60.71% | 47.62% |

## 分合同概览

### 1-品牌球馆冠名合作协议

| Participant | Policy | TP | FP | TN | FN |
|---|---|---:|---:|---:|---:|
| third_party | policy_a | 11 | 6 | 31 | 0 |
| third_party | policy_b | 17 | 0 | 31 | 0 |
| final_applied | policy_a | 8 | 22 | 15 | 3 |
| final_applied | policy_b | 12 | 18 | 13 | 5 |
| agent | policy_a | 8 | 23 | 14 | 3 |
| agent | policy_b | 12 | 19 | 12 | 5 |

### 2-服务协议

| Participant | Policy | TP | FP | TN | FN |
|---|---|---:|---:|---:|---:|
| third_party | policy_a | 2 | 9 | 5 | 0 |
| third_party | policy_b | 7 | 4 | 5 | 0 |
| final_applied | policy_a | 1 | 9 | 5 | 1 |
| final_applied | policy_b | 6 | 4 | 5 | 1 |
| agent | policy_a | 0 | 0 | 14 | 2 |
| agent | policy_b | 0 | 0 | 9 | 7 |

### 3-保密协议

| Participant | Policy | TP | FP | TN | FN |
|---|---|---:|---:|---:|---:|
| third_party | policy_a | 0 | 7 | 6 | 0 |
| third_party | policy_b | 4 | 3 | 6 | 0 |
| final_applied | policy_a | 0 | 6 | 7 | 0 |
| final_applied | policy_b | 3 | 3 | 6 | 1 |
| agent | policy_a | 0 | 0 | 13 | 0 |
| agent | policy_b | 0 | 0 | 9 | 4 |

## 解析告警

- 2-服务协议/2-第三方平台审查结果/Alpha GPT/A-关于《服务协议》的审查意见书: conversion failed (docling_error)
- 3-保密协议/2-第三方平台审查结果/关于《保密协议》的审查意见书: conversion failed (docling_error)
- 1-品牌球馆冠名合作协议: 2 label entries unmatched to clauses
- 1-品牌球馆冠名合作协议/third_party: 15 predictions unmatched
- 1-品牌球馆冠名合作协议/agent: 16 predictions unmatched
- 2-服务协议: 5 label entries unmatched to clauses
- 2-服务协议/third_party: 2 predictions unmatched
- 2-服务协议/final_applied: 1 predictions unmatched
- 3-保密协议: 2 label entries unmatched to clauses
- 3-保密协议/third_party: 10 predictions unmatched
- 3-保密协议/final_applied: 8 predictions unmatched
