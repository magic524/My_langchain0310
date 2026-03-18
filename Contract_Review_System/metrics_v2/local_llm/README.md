# metrics_v2 local_llm

这个目录用于接本地模型接口，完成以下流程：

1. 读取 `Contract_Review_System/metrics_v2/.env`
2. 把整份原合同 markdown 全文送入本地模型
3. 要求模型输出结构化风险点 JSON
4. 将模型输出转成 `metrics_v2` 可评估的数据格式
5. 生成包含 `third_party` / `final_applied` / `local_llm` 的评估报告

## 当前约束

- 不跨项目调用 `v1`
- 只复用 `metrics_v2` 自己的构数和评估模块
- prompt 明文写在脚本里，便于后续调参
- 当前阶段遵循 mentor 要求：整份合同全文输入模型，不做分块推理优化

## 环境变量

默认读取：

- `Contract_Review_System/metrics_v2/.env`

需要的字段与 v1 保持兼容：

- `OPENAI_LLM_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- `OPENAI_TEMPERATURE`
- `OPENAI_EXTRA_BODY`

## 运行命令

```bash
python Contract_Review_System/metrics_v2/local_llm/run_full_contract_eval.py --run-id 20260317_word2md_eval
```

如果你在 conda 环境里跑：

```bash
conda activate langchain
python Contract_Review_System/metrics_v2/local_llm/run_full_contract_eval.py --run-id 20260317_word2md_eval
```

如果模型已经跑过，但想基于现有 `raw_responses` 重新解析和重算分数：

```bash
python Contract_Review_System/metrics_v2/local_llm/run_full_contract_eval.py --run-id 20260317_word2md_eval --reuse-raw-responses
```

如果只想测某一份合同，可以加 `--contract-filter`，按 `contract_id` 子串过滤：

```bash
python Contract_Review_System/metrics_v2/local_llm/run_full_contract_eval.py --run-id 20260317_word2md_eval --reuse-raw-responses --contract-filter "1-品牌球馆冠名合作协议"
```

## 产物

默认输出到：

- `Contract_Review_System/metrics_v2/local_llm/outputs/<run_id>/`

其中包含：

- `debug_requests/<contract_id>.request.json`
- `raw_responses/<contract_id>.txt`
- `local_llm_predictions.json`
- `dataset_with_local_llm.json`
- `evaluation_report.md`
- `evaluation_result.json`

如果本地模型返回 `HTTP 500`，脚本会自动再试一次“去掉 `OPENAI_EXTRA_BODY`”的降级请求。
