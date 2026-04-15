# Contract_Review_System

当前合同审查系统主线整理为 3 个一级子项目：

```text
Contract_Review_System/
├─ main.py
├─ README.md
├─ core/
├─ gui/
├─ pipeline/
├─ word2md/
└─ __init__.py
```

## 环境安装

先创建并激活独立的 conda 环境，再安装主依赖：

```powershell
conda create -n CRS python=3.11 -y
conda activate CRS
pip install -r Contract_Review_System/requirements.txt
```

说明：

- 这份 `requirements.txt` 覆盖 `Contract_Review_System` 的必需功能，包含格式转换、GUI 和 Word 批注导出所需依赖。
- 如果你的终端当前已经在 `Contract_Review_System` 目录下，也可以直接执行 `pip install -r requirements.txt`。
- 后续所有示例都默认在 `CRS` 环境中运行。

## 子项目职责

### 1. `word2md`

负责格式转换。

- 输入：原始 `doc/docx/pdf`
- 输出：统一结构的 `output.md + meta.json + run_summary.json`
- 默认输出根目录：`data/contract_review_outputs/word2md`

### 2. `core/v1`

负责正式 v1 审查主链路。

- 输入：某次 `word2md` 结果
- 输出：`crsv1_result.json`、`risk_statistics.json`、`审查报告.md`、`原合同批注版_CRSv1`
- 默认输出根目录：`Contract_Review_System/core/v1/outputs`

### 3. `pipeline`

负责生产流水线编排。

- 输入：单个或多个原合同 `doc/docx/pdf`
- 输出：`crsv1_result.json`、`审查报告.docx`、批注版 Word、`_artifacts/`
- 默认输出根目录：`Contract_Review_System/pipeline/outputs`

### 4. `gui`

负责合同审查的桌面操作入口。

- 输入：单个原合同 `doc/docx/pdf`
- 输出：沿用生产流水线的批注版 Word、审查报告与运行摘要
- 默认输出根目录：`Contract_Review_System/gui/outputs`

## 推荐运行顺序

### 第一步：启动项目根入口

根目录入口默认启动 GUI：

```powershell
conda activate CRS
python Contract_Review_System/main.py
```

如需单独运行格式转换：

```powershell
conda activate CRS
python Contract_Review_System/word2md/main.py `
  --input data/合同数据-2026.3.12 `
  --recursive `
  --output contract_md_260323
```

说明：

- `--input`：原始合同目录，或单个 `doc/docx/pdf` 文件
- `--output`：本次转换批次名

### 第二步：运行 core/v1 正式审查链路

```powershell
conda activate CRS
python Contract_Review_System/core/v1/main.py `
  --input contract_md_260323 `
  --output 20260408_crsv1
```

GUI 已经由根入口 `Contract_Review_System/main.py` 启动。

## 环境约定

统一使用：

```powershell
conda activate CRS
```

## 输出目录约定

现在 `word2md` 转换结果写到 `Contract_Review_System/data/contract_review_outputs/`，`core/v1`、`pipeline` 和 `gui` 的运行产物都写到各自项目目录下的 `outputs/`，并通过 `.gitignore` 管理。

```text
Contract_Review_System/data/contract_review_outputs/
└─ word2md/

Contract_Review_System/core/v1/outputs/
Contract_Review_System/pipeline/outputs/
Contract_Review_System/gui/outputs/
```

## 维护原则

- 代码目录只保留长期维护的主线项目
- 一次性实验脚本、临时缓存、旧版试验目录应及时移除
- 历史 `word2md` 结果统一放到 `Contract_Review_System/data/contract_review_outputs/word2md/` 下管理
