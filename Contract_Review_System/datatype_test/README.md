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

## AI 对话识别测试（新）

为下一步合同审查 agent 做准备，新增 `chat_md_test.py`：

- 输入：`convert.py` 生成的 `output.md`
- 方式：两轮对话自动测试（结构化抽取 + 自检对话）
- 输出：
    - `reports/{timestamp}_chat_test_{sample_id}.md`（可读报告）
    - `reports/{timestamp}_chat_test_{sample_id}.json`（结构化结果）

### 1) 自动评分模式（推荐）

```powershell
# 方式 A：按 run_id + sample_id 自动定位 output.md
python chat_md_test.py --run-id 20260314_fixcheck --sample-id 1-brand-venue

# 方式 B：直接指定 Markdown 路径
python chat_md_test.py --md-path outputs/20260314_fixcheck/1-brand-venue/output.md
```

### 2) 手动多轮对话模式

```powershell
python chat_md_test.py --run-id 20260314_fixcheck --sample-id 1-brand-venue --interactive
```

### 3) .env 兼容约定（参考 v1 接口风格）

脚本读取 `datatype_test/.env`，兼容以下变量：

- `OPENAI_API_BASE` / `OPENAI_BASE_URL`
- `OPENAI_API_KEY`（本地网关可为 `EMPTY`）
- `OPENAI_LLM_MODEL` / `OPENAI_MODEL_NAME` / `OPENAI_MODEL`
- `OPENAI_TEMPERATURE`
- `OPENAI_EXTRA_BODY`（JSON，可选）

说明：本脚本与 v1 完全独立，不调用 v1 包，仅参考其 OpenAI 兼容接口设计与环境变量命名。

---

## Markdown 专用转换（新）

新增 `convert_md.py`，用于直接生产模型输入的 Markdown：

- 仅输出 `output.md` + `meta.json`
- 不输出 HTML/JSON
- 不生成对比汇总报告
- 目录模式下保持输入子目录层级（输出路径镜像输入路径）
- 自动抽取 Word 批注并“就地”注入到 Markdown 对应段落附近（不再单独尾部贴全量批注）
- 自动抽取 Word 样式提示（颜色/高亮/下划线/斜体）并就地注入，减少关键信息丢失

### 单文件转换

```powershell
python convert_md.py --input-file data/合同数据-2026.3.12/2-服务协议/1-原合同-服务协议.docx
```

### 文件夹批量转换

```powershell
# 仅当前目录
python convert_md.py --input-dir data/合同数据-2026.3.12/2-服务协议

# 递归子目录
python convert_md.py --input-dir data/合同数据-2026.3.12 --recursive
```

### 常用可选参数

- `--output-dir`：指定输出根目录（默认 `datatype_test/outputs_md`）
- `--run-id`：手工指定运行批次 ID
- `--no-postprocess`：关闭 Markdown 轻量纠偏（默认开启）

输出目录示例：

```txt
outputs_md/{run_id}/{sample_id}/output.md
outputs_md/{run_id}/{sample_id}/meta.json
outputs_md/{run_id}/run_summary.json
```

目录镜像示例（递归模式）：

```txt
输入: data/合同数据-2026.3.12/1-品牌球馆冠名合作协议/2-第三方平台审查结果/Alpha GPT/修订批注版-品牌球馆冠名合作协议.docx
输出: outputs_md/{run_id}/1-品牌球馆冠名合作协议/2-第三方平台审查结果/Alpha GPT/修订批注版-品牌球馆冠名合作协议/output.md
```

批注与样式输出说明：

- `output.md` 中默认采用“行内追加”模式，在命中原文行尾直接附加：
    - `（批注#comment_id/段落n/作者xxx: 批注内容）`
    - `（样式/段落n: color#RRGGBB, highlight:yellow, underline ...）`
- 若命中行是 Markdown 表格行，为避免破坏表格结构，会在表格行后单独追加一行括号注记。
- `meta.json` 新增字段：
    - `comment_anchor_count`
    - `comment_anchors`（包含 `comment_id`、`author`、`comment_text`、`paragraph_index`、`paragraph_excerpt`）
    - `style_hint_count`
    - `style_hints`
    - `inline_injection`（匹配成功/未命中统计）

关于 Docling 与样式保真：

- Docling 导出 Markdown 对结构（标题、列表、表格）保留较好。
- 但 Markdown 语法本身无法完整表达字体颜色、字号、字重等 Word 细节。
- 因此脚本采用“样式提示锚注”折中方案，把关键样式作为结构化提示附到对应段落，便于模型判断。

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
