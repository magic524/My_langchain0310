# Contract Review System Project Flow

## 1. Project Goal

This `metrics` subproject evaluates contract review quality with a fixed pipeline:

1. Convert source contract materials to Markdown in `datatype_test`.
2. Build a unified evaluation dataset in `metrics`.
3. Load participant outputs:
   - `third_party`
   - `final_applied`
   - `agent`
4. Align all risks to clause-level units.
5. Compute identification, explanation, and suggestion metrics.
6. Export markdown/json/csv reports.

The current focus is prompt-only review ability. `v1` retrieval mode is not part of the default benchmark.

## 2. End-to-End Data Flow

### Step A. Markdown conversion

Input root:

- `data/...`

Converted output root:

- `Contract_Review_System/datatype_test/outputs_md/<md_run_id>`

Each contract usually contains:

- `1-原合同.../output.md`
- `2-第三方平台审查结果.../output.md`
- `3-最终审查意见.../output.md`
- `4-采纳情况说明.../output.md`

### Step B. Dataset building

Entry script:

- [build_dataset.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/build_dataset.py)

Core module:

- [dataset_builder.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/src/contract_metrics/dataset_builder.py)

What it does:

- Reads `run_summary.json` under one `md_run_id`
- Groups files by contract
- Parses original contract into clauses
- Parses adoption notes into labels
- Selects and parses `third_party` and `final_applied` baselines
- Writes one dataset JSON

Output:

- `Contract_Review_System/metrics/outputs/datasets/dataset_<md_run_id>.json`

### Step C. Evaluation

Entry script:

- [evaluate.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/evaluate.py)

Core module:

- [evaluator.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/src/contract_metrics/evaluator.py)

What it does:

- Loads one dataset JSON
- Loads selected participants
- Converts participant risks to clause-level predictions
- Computes policy A and policy B metrics

### Step D. One-shot run

Prompt-only one-shot:

- [run_prompt_eval.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/run_prompt_eval.py)

Global-context prompt run:

- [run_global_eval.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/run_global_eval.py)

Important:

- These scripts may use different `md_run_id`
- Different `md_run_id` means different dataset contents
- Different dataset contents mean baseline aggregate results can change

## 3. Why Baseline Results Sometimes Change

`third_party` and `final_applied` are deterministic only when all of the following stay the same:

1. same dataset JSON
2. same parsing code
3. same thresholds/config
4. same selected participants set does not change the dataset itself

If the dataset changes, the baseline totals can change even if the source contract family looks similar.

Typical causes:

- different `md_run_id`
- different number of contracts in dataset
- different markdown conversion success/failure
- parser code changed between runs
- selected baseline file changed because source files changed

## 4. Reproducibility Rule

For `third_party` and `final_applied`, results should be stable when:

- input dataset file path is identical
- code version is identical
- config thresholds are identical
- no LLM judge is enabled

Under those conditions, the evaluation is rule-based and should be reproducible.

## 5. Practical Debug Order

When two reports differ, check in this order:

1. compare `dataset_path`
2. compare `dataset.meta.contracts`
3. compare `participants`
4. compare `warnings`
5. compare parser code version
6. compare thresholds in `defaults.json`

## 6. Recommended Daily Commands

Build dataset:

```powershell
conda activate langchain
python Contract_Review_System/metrics/scripts/build_dataset.py --md-run-id 20260316_105814
```

Evaluate only baselines:

```powershell
python Contract_Review_System/metrics/scripts/evaluate.py `
  --dataset Contract_Review_System/metrics/outputs/datasets/dataset_20260316_105814.json `
  --participants third_party,final_applied
```

Run prompt-only full benchmark:

```powershell
python Contract_Review_System/metrics/scripts/run_prompt_eval.py `
  --md-run-id 20260316_105814 `
  --participants third_party,final_applied,agent
```

## 7. Current Judgment

At the current stage, the main source of confusion is not random scoring logic.
The bigger issue is mixed use of different datasets and run modes in historical reports.
