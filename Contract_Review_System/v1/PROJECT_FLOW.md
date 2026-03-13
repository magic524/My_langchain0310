# 合同审查 v1 — 项目流程（通俗说明）

## 简介
本项目位于 `Contract_Review_System/v1`，目标是对合同文本进行自动审查，生成审查建议并对结果做指标化评估（如风险点识别、风险解释准确率、修改建议准确率）。本版本是“prompt-only”实现（即主要通过设计 prompt 与 LLM 交互来得到审查输出）。

**当前是否用到 prompt？**
- 是的：本系统 v1 为 prompt-only（仅通过 prompt 调用模型生成审查结果），评测报告中也写明“本系统 v1（prompt-only）”。

## 高层流程概览（通俗）
1. 数据准备：把原始合同文档拆成段/条款，生成评测用的 JSON 数据集。脚本为 `prepare_real_dataset.py`。
2. 运行审查：对每个段落/条款，按照预设的 prompt 模板调用模型，输出审查意见（审查报告）。脚本为 `run_formal_review.py`（生成 Markdown 报告等）。
3. 评估比对：将模型输出与参考答案（人工标注/历史审查意见）进行比对，计算各项指标（准确率、漏报率、解释/建议得分等）。脚本为 `run_eval.py`。
4. 汇总输出：生成审查报告（`review_report.md`）和评测指标（`evaluation_metrics.md`）等结果文件，存放在 `outputs/formal_runs/<run_id>/` 下。

## 关键脚本和文件（位置与作用）
- [Contract_Review_System/v1/scripts/prepare_real_dataset.py](Contract_Review_System/v1/scripts/prepare_real_dataset.py)
  - 将 `data/合同数据-...` 下的 Word/Docx 等合同源文件拆成段落/条款，输出 JSON 评测数据集。
- [Contract_Review_System/v1/scripts/run_formal_review.py](Contract_Review_System/v1/scripts/run_formal_review.py)
  - 针对数据集中的每一条输入，使用 prompt 调用模型生成审查意见，保存为 Markdown 报告（如 `review_report.md`）。
- [Contract_Review_System/v1/scripts/run_eval.py](Contract_Review_System/v1/scripts/run_eval.py)
  - 将模型输出与参考答案对齐并计算评测指标，输出 `evaluation_metrics.md` 等。
- 输出示例文件（由运行生成）：
  - [Contract_Review_System/v1/outputs/formal_runs/run3/review_report.md](Contract_Review_System/v1/outputs/formal_runs/run3/review_report.md)
  - [Contract_Review_System/v1/outputs/formal_runs/run3/evaluation_metrics.md](Contract_Review_System/v1/outputs/formal_runs/run3/evaluation_metrics.md)

## 复现实验（常用命令示例）
1. 准备数据集（示例命令，终端历史有类似调用）：

```powershell
python Contract_Review_System/v1/scripts/prepare_real_dataset.py \
  --input-root data/合同数据-2026.3.12 \
  --output Contract_Review_System/v1/data/real_eval_dataset_full.json \
  --all-paragraphs
```

2. 运行正式审查（示例）：

```powershell
python Contract_Review_System/v1/scripts/run_formal_review.py \
  --dataset Contract_Review_System/v1/data/real_eval_dataset_full.json \
  --out-dir Contract_Review_System/v1/outputs/formal_runs/run3
```

3. 评估模型输出：

```powershell
python Contract_Review_System/v1/scripts/run_eval.py \
  --preds Contract_Review_System/v1/outputs/formal_runs/run3/predictions.json \
  --refs Contract_Review_System/v1/data/real_eval_dataset_full.json \
  --out Contract_Review_System/v1/outputs/formal_runs/run3/evaluation_metrics.md
```

（以上命令根据脚本参数可能略有不同，请以脚本内 `--help` 为准。）

## 输出文件说明（典型）
- `review_report.md`：对单个合同的逐条审查意见（易读的 Markdown 报告），用于人工复核与回写到 Word。示例位于 `outputs/formal_runs/run3/`。
- `evaluation_metrics.md`：对整套预测结果的量化评估报告，包含准确率、误报/漏报率、解释与建议的得分统计。示例位于 `outputs/formal_runs/run3/`。
- `predictions.json` / `preds`：模型针对每个输入段落的原始输出，供评估脚本使用。

## 细节提示（便于理解）
- Prompt-only：v1 通过 prompt 直接与 LLM 交互，不包含复杂的微调或训练环节；后续版本可能会引入 RAG、检索增强或微调。
- 知识库与历史材料：项目会把历史审查意见、修订版等作为参考片段抓取到上下文，帮助模型生成更一致的审查建议（这些参考材料在 `data/合同数据-...` 中）。
- 评测逻辑：先做风险点识别（是否检测到风险），再对“风险解释”和“修改建议”做相似度/得分判定，从而输出指标（如示例 `evaluation_metrics.md` 所示）。

## 快速排查与下一步建议
- 若想确认是否真为 prompt-only：查看 `run_formal_review.py` 中调用模型的实现（提示模板、调用参数）。
- 若要改进效果：考虑加入检索（RAG）或对 prompt 与模板做 A/B 测试；或用微调/指令微调提升一致性。

---
文件已生成于本仓：`Contract_Review_System/v1/PROJECT_FLOW.md`，可直接打开查看和修改。
