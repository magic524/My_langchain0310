### 1) Full_eval

```powershell
python .\Contract_Review_System\datatype_test\convert_md.py --input-dir .\data\合同数据-2026.3.12 --recursive --output-dir .\Contract_Review_System\datatype_test\outputs_md --run-id 20260316_full_eval
```

```powershell
python .\Contract_Review_System\metrics\scripts\build_dataset.py --md-run-id 20260316_full_eval
```

```powershell
python .\Contract_Review_System\metrics\scripts\run_prompt_eval.py --md-run-id 20260316_full_eval --participants third_party,final_applied,agent --output-dir .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_one_shot
```

```powershell
python .\Contract_Review_System\metrics\scripts\report.py --evaluation-json .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_one_shot\evaluation_payload.json --output-dir .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_one_shot
```
