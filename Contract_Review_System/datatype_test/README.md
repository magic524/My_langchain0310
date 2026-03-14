# 合同文档格式保真测试 (datatype_test)

> **目标**：验证 `.doc/.docx` 合同原文通过 [Docling](https://github.com/DS4SD/docling) 转换为 Markdown、HTML、JSON 三种格式后，对合同原始格式的保真情况，为 v2 开发确定输入数据格式。

---

## 背景

v1 版本使用 `Docx2txtLoader`（LangChain）+ XML 段落抽取将合同转为纯文本传给 LLM，导致以下格式信息丢失：

| 丢失内容 | v1 影响 |
|---------|---------|
| 表格（行/列/单元格）| 费用条款、责任矩阵完全丢失 |
| 标题/章节层级 | 无法识别章节结构 |
| 修订/批注 | 原始格式混入，无法精确解析 |
| 列表编号 | 平铺为段落，层级消失 |

本测试子项目**完全独立于 v1**，不调用其代码，不依赖其数据集。

---

## 目录结构

```
datatype_test/
├── README.md            ← 本文档
├── requirements.txt     ← 环境依赖
├── samples.json         ← 测试样本清单（每类合同各 1 份）
├── convert.py           ← 主转换脚本（Docling 调用 + 多格式导出 + 元数据记录）
├── experiment_log.md    ← 实验日志（每次运行手工追加结论）
├── outputs/             ← 转换产物（自动生成，按 run_id 组织）
│   └── {run_id}/
│       └── {sample_id}/
│           ├── output.md     ← Markdown 格式导出
│           ├── output.html   ← HTML 格式导出
│           ├── output.json   ← 结构化 JSON 导出
│           └── meta.json     ← 本次转换元数据
└── reports/             ← 人工对比报告（自动生成）
    └── {run_id}_summary.md  ← 汇总对比报告（按四维度分析 + 首轮结论）
```

---

## 对比维度

每次测试按如下四个维度评估格式保真度，结果写入 `reports/{run_id}_summary.md`：

| 维度 | 验证重点 |
|------|---------|
| **表格结构保留** | 行数/列数是否可辨识；标题行/单元格文本是否完整 |
| **标题与层级保留** | 章节标题是否区分为 Heading；编号层级是否维持（一、1. 1.1 等） |
| **修订/批注保留** | Track changes、批注内容是否出现在输出中 |
| **纯文本完整度** | 是否存在乱码、截断、重复或词序错乱 |

---

## 快速开始

```powershell
# 激活环境
conda activate langchain

# 进入测试目录
cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test

# 运行全量转换（生成 Markdown + HTML + JSON + 汇总报告）
python convert.py

# 只转换指定样本（用 samples.json 中的 id）
python convert.py --sample-id 1-brand-venue --formats md html

# 查看可选参数
python convert.py --help
```

---

## doc 文件处理策略

对于 `.doc` 格式（保密协议），脚本按以下优先级尝试转换为 `.docx`，再送入 Docling：

1. **LibreOffice soffice**（推荐，跨平台）：`soffice --headless --convert-to docx`
2. **Win32com / Word COM**（Windows + Office）：调用 Word 程序 API 另存
3. 若两者均不可用 → 记录到 `meta.json`，在汇总报告中标注 `⚠️ 转换失败`

---

## 首轮样本清单

| 样本 ID | 文件类型 | 来源 | 预期挑战点 |
|---------|---------|------|-----------|
| `1-brand-venue` | `.docx` | 品牌球馆冠名合作协议 | 合同金额/权益条款（可能含表格） |
| `2-service` | `.docx` | 服务协议 | 多层级编号条款 |
| `3-nda` | `.doc` | 保密协议 | doc 兼容性 + 保密范围条款 |

---

## 实验结论入口

每次运行后，详细结论记录在：

- `experiment_log.md` — 时间线视角，逐次记录运行参数、发现与下一步
- `reports/{run_id}_summary.md` — 按样本和维度的结构化对比报告

---

## 与 v2 的关系

本测试的**输出结论**将直接用于 v2 格式选型决策：
- 主格式：推荐 Markdown（若表格保真度满足要求）或 HTML（若需要更完整排版信息）
- 备选格式：JSON（用于程序化段落拆分和结构化分析）
- 若 Docling 修订/批注保留不足，v2 阶段将补充 python-docx 融合方案
