# tests

`tests` 是合同审查系统的评测与报告子项目，负责消费 `word2md` 与 `local_llm` 产物，并输出可追溯的评测结果与三方对照。

## 这个子项目负责什么

- 从 `word2md` 的 `run_id` 目录构建统一数据集
- 解析原合同、第三方审查结果、最终审查意见、采纳说明
- 计算条款级和风险点级指标
- 输出 `evaluation_result.json` 与 `evaluation_report.md`
- 当数据集中包含 `local_llm` 参与方时，输出三方对照与总体汇总

## 这个子项目不负责什么

- 不直接调用本地模型 API
- 不维护 prompt 实验脚本
- 不再存放一次性试验输出目录

## 默认输入输出

- 默认读取：`data/contract_review_outputs/word2md/<run_id>`
- 默认数据集输出：`Contract_Review_System/tests/outputs/datasets/dataset_<run_id>.json`
- 默认评测输出：`Contract_Review_System/tests/outputs/eval_runs/<run_id>/`

## 环境

```powershell
conda activate langchain
```

## 常用命令

先构建数据集：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py --run-id 20260317_word2md_eval
```

如需显式指定某次 `word2md` 跑批目录：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/build_dataset.py --run-id 20260317_word2md_eval --word2md-run-dir "data/contract_review_outputs/word2md/20260317_word2md_eval"
```

再执行评测：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py --run-id 20260317_word2md_eval
```

只评测指定参与方：

```powershell
conda activate langchain
python Contract_Review_System/tests/scripts/evaluate.py --run-id 20260317_word2md_eval --participants third_party,final_applied
```

## 核心产物

- `dataset_<run_id>.json`：统一数据集
- `evaluation_result.json`：完整机器可读评测结果
- `evaluation_report.md`：人工可读评测报告

## 目录说明

```text
tests/
├── docs/
├── scripts/
├── src/contract_tests/
└── tests/
```

## 维护约定

- 评测逻辑只依赖 `word2md` 产物，不直接依赖旧试验目录
- 如需扩展到更多参与方，优先在 `src/contract_tests/` 内补齐解析与匹配逻辑
- `only_prompt_local_llm` 只负责生成 `local_llm` 结果与原合同批注版；评测与对照统一放在本项目
