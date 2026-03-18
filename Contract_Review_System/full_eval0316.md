### 1) Full_eval — 公共前置步骤（两种策略共用）

```powershell
python .\Contract_Review_System\datatype_test\convert_md.py --input-dir .\data\合同数据-2026.3.12 --recursive --output-dir .\Contract_Review_System\datatype_test\outputs_md --run-id 20260316_full_eval
```

```powershell
python .\Contract_Review_System\metrics\scripts\build_dataset.py --md-run-id 20260316_full_eval
```

---

### 2) 策略 A：逐条款 prompt_only（无全局上下文）

```powershell
python .\Contract_Review_System\metrics\scripts\run_prompt_eval.py --md-run-id 20260316_full_eval --participants third_party,final_applied,agent --output-dir .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_one_shot
```

```powershell
python .\Contract_Review_System\metrics\scripts\report.py --evaluation-json .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_one_shot\evaluation_payload.json --output-dir .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_one_shot
```

---

### 3) 策略 B：全局上下文两阶段（Stage1 全文扫描 + Stage2 带上下文逐条精审）

```powershell
python .\Contract_Review_System\metrics\scripts\run_global_eval.py --md-run-id 20260316_full_eval --participants third_party,final_applied,agent --output-dir .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_global_shot
```

```powershell
python .\Contract_Review_System\metrics\scripts\report.py --evaluation-json .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_global_shot\evaluation_payload.json --output-dir .\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_global_shot
```

---

### 4) 对比报告产物

| 产物 | 路径 |
|---|---|
| 逐条款报告 | `.\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_one_shot\evaluation_report.md` |
| 全局上下文报告 | `.\Contract_Review_System\metrics\outputs\eval_runs\20260316_full_eval_global_shot\evaluation_report.md` |
