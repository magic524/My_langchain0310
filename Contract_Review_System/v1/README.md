# Contract Review System v1

v1 目标：先建立可复现的对比评测体系，在不使用其它合同作为参考的前提下，比较三类输出：

1. 第三方平台
2. 他们的最终应用版
3. 本地 LLM prompt-only（本系统 v1）

## 目录

- src/contract_review_v1/schema.py: 数据集与结构化对象
- src/contract_review_v1/runner.py: 本地 LLM 调用与输出解析
- src/contract_review_v1/metrics.py: 三类指标计算
- src/contract_review_v1/reporting.py: Markdown + JSON 报告输出
- scripts/run_eval.py: 执行入口
- data/sample_eval_dataset.json: 样例数据

## 数据格式

每条 clause 至少包含：

- contract_id
- clause_id
- clause_text
- ground_truth: 人工最终采纳版真值
- third_party: 第三方平台结果
- final_applied: 他们最终应用版结果
- explanation_keywords
- suggestion_keywords

## 指标定义

1. 风险点识别
- 准确率: (TP + TN) / 全部
- 漏报率: FN / (TP + FN)
- 误报率: FP / (FP + TN)

2. 风险解释准确率
- 规则评分：解释文本对关键字覆盖率（默认阈值 0.8）
- 报告中输出正确示例与错误示例

3. 修改建议准确率
- 规则评分：建议关键字覆盖率 * 0.7 + 可执行性 * 0.3（默认阈值 0.75）
- 报告中输出正确示例与错误示例

## 运行

Windows + conda 环境示例：

```powershell
conda activate langchain
cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\v1
python scripts/run_eval.py --dataset data/sample_eval_dataset.json --output-dir outputs
```

如果暂时只想验证评测流程，不调用本地模型：

```powershell
python scripts/run_eval.py --dataset data/sample_eval_dataset.json --output-dir outputs --skip-system
```

执行后会生成：

- outputs/evaluation_report.md
- outputs/evaluation_detail.json

## 真实合同数据转换

如果你的真实合同目录为 `data/合同数据-2026.3.12`，可先自动转换为评测 JSON：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/prepare_real_dataset.py --input-root data/合同数据-2026.3.12 --output Contract_Review_System/v1/data/real_eval_dataset.json
```

如果担心启发式筛选遗漏信息，可使用全量条款模式：

```powershell
python Contract_Review_System/v1/scripts/prepare_real_dataset.py --input-root data/合同数据-2026.3.12 --output Contract_Review_System/v1/data/real_eval_dataset.json --keep-all-clauses
```

生成后的数据中会包含 `conversion_trace`，记录候选条款数、入选条款数和被过滤条款预览。

然后运行评测：

```powershell
python Contract_Review_System/v1/scripts/run_eval.py --dataset Contract_Review_System/v1/data/real_eval_dataset.json --output-dir Contract_Review_System/v1/outputs/real
```

如需先验证流程不调用模型：

```powershell
python Contract_Review_System/v1/scripts/run_eval.py --dataset Contract_Review_System/v1/data/real_eval_dataset.json --output-dir Contract_Review_System/v1/outputs/real --skip-system
```

## 正式审查运行（run1/run2 输出）

如果你要用“1-品牌球馆冠名合作协议”做测试，使用“2-服务协议”和“3-保密协议”做知识库，可运行：

```powershell
conda activate langchain
python Contract_Review_System/v1/scripts/run_formal_review.py --data-root data/合同数据-2026.3.12 --test-prefix 1- --knowledge-prefixes 2- 3- --output-root Contract_Review_System/v1/outputs/formal_runs
```

每次运行会自动新建 `run1`、`run2`... 目录，并输出：

- `review_report.md`：与 `contract_review_agent.py` 同风格的详细审查报告
- `run_meta.json`：本次运行参数、模型、输入输出文件清单

## 下一步

v1 跑通后，建议按留一法扩展三份合同数据；v2 再引入知识库检索，保持同一评测口径对比增益。
