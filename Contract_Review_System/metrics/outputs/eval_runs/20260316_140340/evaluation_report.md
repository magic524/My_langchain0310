# Contract Metrics Evaluation Report

## 概览

- 数据集: `E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\metrics\outputs\datasets\dataset_20260316_105814.json`
- 参与方: third_party, agent
- LLM 裁判: 关闭
- 警告数: 9

## 口径A（采纳+部分采纳为正例）

| Participant | Risk Accuracy | Miss Rate | False Positive Rate | Explanation Direction | Explanation Accuracy | Explanation Completeness | Suggestion Direction | Suggestion Accuracy | Suggestion Completeness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| agent | 61.04% | 46.15% | 37.50% | 0.00% | 0.00% | 46.43% | 42.86% | 40.83% | 64.75% |
| third_party | 71.43% | 0.00% | 34.38% | 84.62% | 15.38% | 48.08% | 84.62% | 84.62% | 69.23% |

## 口径B（全部意见为正例）

| Participant | Risk Accuracy | Miss Rate | False Positive Rate | Explanation Direction | Explanation Accuracy | Explanation Completeness | Suggestion Direction | Suggestion Accuracy | Suggestion Completeness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| agent | 54.55% | 57.14% | 38.78% | 0.00% | 1.27% | 56.25% | 50.00% | 38.03% | 62.37% |
| third_party | 90.91% | 0.00% | 14.29% | 60.71% | 14.29% | 38.39% | 71.43% | 60.71% | 47.62% |

## 分合同概览

### 1-品牌球馆冠名合作协议

| Participant | Policy | TP | FP | TN | FN |
|---|---|---:|---:|---:|---:|
| third_party | policy_a | 11 | 6 | 31 | 0 |
| third_party | policy_b | 17 | 0 | 31 | 0 |
| agent | policy_a | 7 | 24 | 13 | 4 |
| agent | policy_b | 12 | 19 | 12 | 5 |

### 2-服务协议

| Participant | Policy | TP | FP | TN | FN |
|---|---|---:|---:|---:|---:|
| third_party | policy_a | 2 | 9 | 5 | 0 |
| third_party | policy_b | 7 | 4 | 5 | 0 |
| agent | policy_a | 0 | 0 | 14 | 2 |
| agent | policy_b | 0 | 0 | 9 | 7 |

### 3-保密协议

| Participant | Policy | TP | FP | TN | FN |
|---|---|---:|---:|---:|---:|
| third_party | policy_a | 0 | 7 | 6 | 0 |
| third_party | policy_b | 4 | 3 | 6 | 0 |
| agent | policy_a | 0 | 0 | 13 | 0 |
| agent | policy_b | 0 | 0 | 9 | 4 |

## 解析告警

- 2-服务协议/2-第三方平台审查结果/Alpha GPT/A-关于《服务协议》的审查意见书: conversion failed (docling_error)
- 3-保密协议/2-第三方平台审查结果/关于《保密协议》的审查意见书: conversion failed (docling_error)
- 1-品牌球馆冠名合作协议: 2 label entries unmatched to clauses
- 1-品牌球馆冠名合作协议/third_party: 15 predictions unmatched
- 1-品牌球馆冠名合作协议/agent: 21 predictions unmatched
- 2-服务协议: 5 label entries unmatched to clauses
- 2-服务协议/third_party: 2 predictions unmatched
- 3-保密协议: 2 label entries unmatched to clauses
- 3-保密协议/third_party: 10 predictions unmatched
