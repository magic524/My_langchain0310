# LLM Quality Evaluator (Template-Based)

## Purpose

This folder contains an isolated script to evaluate whether `local_llm` risk explanations and suggestions are close to `third_party` outputs, based on:

- `dataset_with_local_llm.json`
- `template.json`
- local model endpoint via `ChatOpenAI`

The script is intentionally isolated to avoid changing existing evaluation documents.

## Files

- `template.json`: result template provided by user.
- `evaluate_local_vs_thirdparty_by_template.py`: main script.
- `outputs/quality_eval_by_template.json`: generated result.
- `outputs/raw_llm_responses/`: raw model replies for traceability.

## Environment

Use existing environment:

```powershell
conda activate langchain
```

Required packages:

- `langchain-openai`
- `langchain-core`

## Run

```powershell
python Contract_Review_System/metrics_v2/local_llm/llm_quality_evaluator/evaluate_local_vs_thirdparty_by_template.py \
  --dataset-path Contract_Review_System/metrics_v2/local_llm/outputs_fix2/20260317_word2md_eval_third_party_fix2_20260318/contract_runs/1-品牌球馆冠名合作协议/dataset_with_local_llm.json \
  --template-path Contract_Review_System/metrics_v2/local_llm/llm_quality_evaluator/template.json \
  --output-dir Contract_Review_System/metrics_v2/local_llm/llm_quality_evaluator/outputs
```

Optional controls:

- `--match-threshold 0.45`: similarity threshold for pairing local risk with third-party risk.
- `--max-items 0`: evaluate all local risks; set positive number for quick dry run.
- `--openai-api-base`, `--model-name`, `--temperature`, `--top-k` for model runtime.
- `--disable-thinking` to disable `chat_template_kwargs.enable_thinking`.

## Transparent Process

The script prints and stores concise process logs:

1. Read dataset and template.
2. Count local/third-party risks.
3. Pair local risk with best third-party candidate by text similarity.
4. Ask LLM to score `match` fields following `template.json`.
5. Produce `match_results`, `false_positive`, `false_negative` in one JSON output.

This keeps the workflow auditable and avoids black-box behavior.
