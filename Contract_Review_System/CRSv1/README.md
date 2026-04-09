# CRSv1

`CRSv1` 是合同审查系统的正式 v1 审查内核。

它不再沿用 `only_prompt_local_llm` 的“整份合同一次性审查”范式，而是拆成：

- 合同背景抽取
- 父子条款切分
- 以父条款为单位的审查任务
- 风险点组装
- Word 批注导出
- 审查报告导出

## 职责边界

`CRSv1` 负责：

- 消费 `word2md` 产出的 `output.md / meta.json / run_summary.json`
- 对合同生成统一背景摘要
- 构建条款层级树与父条款审查任务
- 调用本地模型输出结构化风险点
- 组装风险统计与报告数据
- 导出带批注 Word 与审查报告

`CRSv1` 不负责：

- 文件格式转换
- 联网检索与诉讼风险查询
- 评测与三方对照

## 当前目录结构

```text
CRSv1/
├─ README.md
├─ main.py
├─ docs/
│  └─ structure.md
└─ src/
   └─ crsv1/
      ├─ __init__.py
      ├─ background_brief.py
      ├─ clause_tree_parser.py
      ├─ cli.py
      ├─ input_adapter.py
      ├─ pipeline.py
      ├─ report_export.py
      ├─ review_executor.py
      ├─ review_prompt_builder.py
      ├─ risk_assembler.py
      ├─ runtime_types.py
      ├─ text_utils.py
      └─ word_comment_export.py
```

## 运行方式

```powershell
conda activate langchain
python Contract_Review_System/CRSv1/main.py `
  --input 20260317_word2md_eval `
  --output demo_crsv1
```

## 主要输出

默认输出目录：

`Contract_Review_System/CRSv1/outputs/<run_name>`

至少包含：

- `crsv1_result.json`
- `review_summary.json`
- `risk_statistics.json`
- `审查报告.md`
- `原合同批注版_CRSv1/`
- `raw_responses/`
- `debug_requests/`

## 环境约定

统一使用：

```powershell
conda activate langchain
```

本地模型接口仍复用：

- `Contract_Review_System/common/local_llm_client.py`
