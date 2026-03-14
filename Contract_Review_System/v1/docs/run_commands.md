# v1 运行命令总表

本文件将 v1 的常用运行命令统一整理在一起，全部采用 Windows + conda 的执行方式。

## 0. 环境准备

在工作区根目录执行：

```powershell
conda activate langchain
cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310
```

公司本地 LLM（vLLM/OpenAI 兼容）推荐先设置以下环境变量：

```powershell
conda activate langchain
$env:OPENAI_API_BASE = "http://10.130.61.231:8001/v1"
$env:OPENAI_BASE_URL = "http://10.130.61.231:8001/v1"
$env:OPENAI_API_KEY = "EMPTY"
$env:OPENAI_LLM_MODEL = "InstructModel"
$env:OPENAI_TEMPERATURE = "0.7"
$env:OPENAI_EXTRA_BODY = '{"top_k":20,"chat_template_kwargs":{"enable_thinking":true}}'
```

可选连通性检查：

```powershell
conda activate langchain
python -c "import os; print(os.getenv('OPENAI_API_BASE')); print(os.getenv('OPENAI_LLM_MODEL'))"
```

## 1. 数据集准备

将真实合同目录转换为评测数据集（常规模式）：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/prepare_real_dataset.py --input-root data/合同数据-2026.3.12 --output Contract_Review_System/v1/data/real_eval_dataset.json
```

全量条款模式（不做启发式筛选）：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/prepare_real_dataset.py --input-root data/合同数据-2026.3.12 --output Contract_Review_System/v1/data/real_eval_dataset_full.json --all-paragraphs
```

## 2. 正式审查（带知识库）

使用 1- 合同测试，2-/3- 作为知识库：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_formal_review.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --knowledge-prefixes 2- 3- --output-root Contract_Review_System/v1/outputs/formal_runs --all-paragraphs --top-k 5 --eval-dataset Contract_Review_System/v1/data/real_eval_dataset_full.json
```

输出目录：
- Contract_Review_System/v1/outputs/formal_runs/runN/review_report.md
- Contract_Review_System/v1/outputs/formal_runs/runN/evaluation_metrics.md
- Contract_Review_System/v1/outputs/formal_runs/runN/evaluation_metrics.json
- Contract_Review_System/v1/outputs/formal_runs/runN/run_meta.json

## 3. 消融实验（独立入口）

一次运行四种模式（full、prompt-only、service-only、nda-only）：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_ablation.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --modes full prompt-only service-only nda-only --output-root Contract_Review_System/v1/outputs/ablation_runs --all-paragraphs --top-k 5 --eval-dataset Contract_Review_System/v1/data/real_eval_dataset_full.json
```

仅运行纯 Prompt 消融：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_ablation.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --modes prompt-only --output-root Contract_Review_System/v1/outputs/ablation_runs --all-paragraphs --top-k 5 --eval-dataset Contract_Review_System/v1/data/real_eval_dataset_full.json
```

说明：`--all-paragraphs` 会对每个段落分别调用一次模型（例如 87 段 = 87 次调用），prompt-only 也会变慢。

更快的调试命令（先用采样模式）：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_ablation.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --modes prompt-only --output-root Contract_Review_System/v1/outputs/ablation_runs --max-paragraphs 15 --top-k 5 --eval-dataset Contract_Review_System/v1/data/real_eval_dataset_full.json
```

进一步提速（跳过评测文件生成）：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_ablation.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --modes prompt-only --output-root Contract_Review_System/v1/outputs/ablation_runs --max-paragraphs 15 --skip-eval
```

若终端会话经常丢失环境变量，建议使用“单条命令内联设置”版本（最稳妥）：

```powershell
conda activate langchain; $env:OPENAI_API_BASE="http://10.130.61.231:8001/v1"; $env:OPENAI_BASE_URL="http://10.130.61.231:8001/v1"; $env:OPENAI_API_KEY="EMPTY"; $env:OPENAI_LLM_MODEL="InstructModel"; $env:OPENAI_TEMPERATURE="0.7"; $env:OPENAI_EXTRA_BODY='{"top_k":20,"chat_template_kwargs":{"enable_thinking":true}}'; python Contract_Review_System/v1/scripts/run_ablation.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --modes prompt-only --output-root Contract_Review_System/v1/outputs/ablation_runs --all-paragraphs --top-k 5 --eval-dataset Contract_Review_System/v1/data/real_eval_dataset_full.json
```

输出目录：
- Contract_Review_System/v1/outputs/ablation_runs/{mode}/{timestamp}/review_report.md
- Contract_Review_System/v1/outputs/ablation_runs/{mode}/{timestamp}/evaluation_metrics.md
- Contract_Review_System/v1/outputs/ablation_runs/{mode}/{timestamp}/evaluation_metrics.json
- Contract_Review_System/v1/outputs/ablation_runs/{mode}/{timestamp}/run_meta.json
- Contract_Review_System/v1/outputs/ablation_runs/summary_{timestamp}.json

## 4. 独立评测

基于指定数据集运行三方对比评测：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_eval.py --dataset Contract_Review_System/v1/data/real_eval_dataset_full.json --output-dir Contract_Review_System/v1/outputs/real
```

只验证评测流程（不调用本地模型）：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_eval.py --dataset Contract_Review_System/v1/data/real_eval_dataset_full.json --output-dir Contract_Review_System/v1/outputs/real --skip-system
```

## 5. 快速自检

查看脚本参数是否正常：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_formal_review.py --help
python Contract_Review_System/v1/scripts/run_ablation.py --help
python Contract_Review_System/v1/scripts/run_eval.py --help
```

## 6. 打印 all-paragraphs 拆分结果

用于查看某次运行中“到底拆成了哪些段落”（例如 87 段）。下面命令会把段落导出成带序号文本文件：

```powershell
conda activate langchain
python -c "from pathlib import Path; import sys; sys.path.insert(0, 'Contract_Review_System/v1/src'); import contract_review_v1.agent_core as m; test_file=Path(r'data/合同数据-2026.3.12/1-品牌球馆冠名合作协议/1-原合同：品牌球馆冠名合作协议.docx').resolve(); parsed=m.parse_word_file(test_file, 'original'); paras=[]; seen=set();
for p in parsed.paragraphs:
 c=m.normalize_whitespace(p)
 if not c or c in seen:
  continue
 paras.append(c); seen.add(c)
out=Path(r'Contract_Review_System/v1/outputs/ablation_runs/prompt-only/20260313_162337/target_paragraphs_87.txt').resolve(); out.parent.mkdir(parents=True, exist_ok=True); out.write_text('\n\n'.join([f'[{i+1:03d}] {t}' for i,t in enumerate(paras)]), encoding='utf-8'); print('count=', len(paras)); print('out=', out)"
```

如果只想快速看前 20 段，可把最后一行改成：

```powershell
... out.write_text('\n\n'.join([f'[{i+1:03d}] {t}' for i,t in enumerate(paras[:20])]), encoding='utf-8') ...
```

## 7. 常见错误避免

- 不要把多个参数粘连成一个字符串，例如把 --output-root 与 --top-k 拼在一起。
- Windows 下建议统一使用正斜杠路径，避免转义问题。
- 先执行 conda activate langchain 再执行 python 命令，确保模型依赖与 langchain 版本一致。

## 8. 双层提示词改法

v1 现已采用双层提示词：

- 系统层：`SYSTEM_PROMPT`（位于 `src/contract_review_v1/agent_core.py`）
- 任务层：`BUSINESS_REVIEW_PROMPT` + `OUTPUT_FORMAT_PROMPT_TEMPLATE`（位于 `src/contract_review_v1/runner.py`）

建议修改原则：

- 业务策略（法律风格、风险偏好）主要改 `BUSINESS_REVIEW_PROMPT`
- 输出字段格式主要改 `OUTPUT_FORMAT_PROMPT_TEMPLATE`
- 不要删除 `目标条款：{clause_text}` 注入，否则每条审查会丢失针对性
- 若继续复用当前评测解析，请保留字段名：`风险级别`、`问题说明`、`建议修改`、`参考依据`（或仅输出 `无需批注`）
