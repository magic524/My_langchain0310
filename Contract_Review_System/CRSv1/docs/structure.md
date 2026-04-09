# CRSv1 结构说明

## 推荐修改位置

- 命令入口改 `src/crsv1/cli.py`
- 主流程编排改 `src/crsv1/pipeline.py`
- 条款树解析改 `src/crsv1/clause_tree_parser.py`
- 本地模型任务执行改 `src/crsv1/review_executor.py`
- 风险组装改 `src/crsv1/risk_assembler.py`
- Word 批注导出改 `src/crsv1/word_comment_export.py`
- 审查报告导出改 `src/crsv1/report_export.py`

## 设计原则

- `CRSv1` 不再把整份合同当成一个审查任务
- 条款树是多任务审查、风险锚定、统计报表的共同基础
- 模型接口先统一成“可并行”的任务模型，首版默认串行执行
- 批注导出和报告导出都直接消费 `CRSv1` 新分层结果
