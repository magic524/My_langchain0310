# Test Report 2026-03-17

## 1. Test Goal

Today's goal is to verify whether the current testing rules are fundamentally wrong, and to explain why historical `final_applied` and `third_party` results look inconsistent across reports.

## 2. Scope

Compared reports:

- [old one-shot report](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/old/20260316_154443_one_shot/evaluation_report.md)
- [old prompt-only report](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/old/20260316_150348_prompt_only/evaluation_report.md)
- [single-brand global-shot report](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/20260316_single_brand_global_shot/evaluation_report.md)

Checked code:

- [build_dataset.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/build_dataset.py)
- [evaluate.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/evaluate.py)
- [run_prompt_eval.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/run_prompt_eval.py)
- [run_global_eval.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/scripts/run_global_eval.py)
- [dataset_builder.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/src/contract_metrics/dataset_builder.py)
- [baseline_parser.py](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/src/contract_metrics/baseline_parser.py)
- [defaults.json](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/config/defaults.json)

## 3. Key Conclusion

The current evaluation logic is not showing obvious random behavior.

The main reason historical `final_applied` and `third_party` values differ is:

- the reports were generated from different datasets
- some runs evaluate 3 contracts, some evaluate only 1 contract
- warnings and conversion failures differ by dataset

So the answer to your question is:

- If the contract data, built dataset JSON, parsing code, and thresholds are all fixed, then `final_applied` and `third_party` results should stay the same.
- The historical reports you compared do not satisfy that condition.

## 4. Evidence

### Report A: old one-shot

Source:

- [RUN_TRACE.md](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/old/20260316_154443_one_shot/RUN_TRACE.md)

Dataset:

- `dataset_20260316_105814.json`

Contracts:

- `3`

Participants:

- `third_party, final_applied`

### Report B: old prompt-only

Source:

- [README_summary.md](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/old/20260316_150348_prompt_only/README_summary.md)

Dataset:

- `dataset_20260316_105814.json`

Contracts:

- `3`

Participants:

- `third_party, agent`

Interpretation:

- `third_party` should match Report A because dataset is the same
- `final_applied` is absent here, so there is nothing to compare

Observed result:

- Report A `third_party / policy_a`: `84.42% / 15.38% / 15.62%`
- Report B `third_party / policy_a`: `84.42% / 15.38% / 15.62%`
- Report A `third_party / policy_b`: `90.91% / 25.00% / 0.00%`
- Report B `third_party / policy_b`: `90.91% / 25.00% / 0.00%`

This is direct evidence that the same dataset produces the same baseline result.

### Report C: single-brand global-shot

Source:

- [README_summary.md](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/outputs/eval_runs/20260316_single_brand_global_shot/README_summary.md)

Dataset:

- `dataset_20260316_full_eval_single_brand.json`

Contracts:

- `1`

Participants:

- `third_party, final_applied, agent`

Interpretation:

- this report is not comparable to Report A as an aggregate baseline report
- it only evaluates the single brand contract, not the 3-contract dataset

## 5. Current Judgment on Testing Rules

### What looks correct

- Dataset building is rule-based.
- Baseline file selection uses sorted paths and explicit priority logic.
- Evaluation itself is rule-based and deterministic.
- Threshold config is fixed in [defaults.json](E:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/metrics/config/defaults.json).

### What is still risky

- Historical reports are easy to misread because dataset scope is not visually prominent enough.
- `final_applied` is not a clean structured risk list in every contract, so it is not a guaranteed high-score upper bound.
- Some markdown conversion failures and unmatched clause mappings still affect results.

## 6. Why `final_applied` Still Looks Strange

This is not only a scoring problem. It is also a data-shape problem.

Observed issues:

- `3-保密协议` had `final_applied parsed 0 risk entries`
- some `final_applied` content is plain revised text or sparse comments
- clause matching is imperfect for some labels and predictions

That means:

- low `final_applied` score does not automatically prove the metric formula is wrong
- it more likely means `final_applied` is a weak proxy for structured prediction in the current parsing pipeline

## 7. Decision for Today

Today's testing conclusion:

1. There is no strong evidence that the metric formulas themselves are randomly wrong.
2. The biggest confusion comes from comparing reports built on different datasets.
3. The biggest evaluation risk now is not formula randomness, but data comparability and parser coverage.
4. `final_applied` should be treated as a baseline source under parsing assumptions, not as unquestioned gold-standard output.

## 8. Recommended Next Actions

To make future tests easier to trust:

1. Freeze one canonical dataset for daily benchmarking, for example `dataset_20260316_105814.json`.
2. Always write dataset path and contract count at the top of every report.
3. Separate two benchmark modes:
   - `full_dataset_benchmark`
   - `single_contract_experiment`
4. Add one consistency check script later:
   - same dataset + same config + no code change -> same baseline scores

## 9. Final Summary

The testing rules are not obviously broken at the formula level.
The current confusion mainly comes from mixing different datasets and run modes when reading old reports.
The next phase should focus on benchmark standardization and parser-quality validation, especially for `final_applied`.
