# word2md

`word2md` 是合同审查系统的格式转换子项目，负责把 `doc/docx/pdf` 合同材料转换为后续评测和模型调用可直接复用的 Markdown 产物。

## 当前目录结构

```text
word2md/
├─ README.md
├─ CHANGELOG.md
├─ docs/
│  └─ structure.md
├─ scripts/
│  └─ main.py
├─ src/word2md/
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ common.py
│  ├─ docx_features.py
│  ├─ markdown_formatter.py
│  ├─ pipeline.py
│  └─ word_processing.py
├─ main.py
├─ common.py
├─ docx_features.py
├─ markdown_formatter.py
├─ pipeline.py
└─ word_processing.py
```

## 每个文件是干嘛的

### 推荐使用的目录

- `scripts/main.py`
  - 推荐命令入口
  - 以后优先从这里启动
- `src/word2md/cli.py`
  - 真正的命令行解析入口
  - 负责 `--input / --output` 等参数解析
- `src/word2md/common.py`
  - 通用路径、默认目录、批次命名、输入文件收集
- `src/word2md/docx_features.py`
  - 从 `docx` 中抽取批注、样式提示、可见段落
- `src/word2md/markdown_formatter.py`
  - Markdown 后处理、编号修复、批注注入
- `src/word2md/pipeline.py`
  - 主流程调度
  - 串起 Docling、Markdown 导出、meta 写入
- `src/word2md/word_processing.py`
  - `doc -> docx` 转换
  - Docling 输入前的预处理
- `docs/structure.md`
  - 结构说明和维护约定

### 兼容保留的文件

- `main.py`
  - 兼容旧命令入口
  - 内部转发到 `src/word2md/cli.py`
- `common.py`
  - 兼容旧导入路径
- `docx_features.py`
  - 历史模块，后续建议只改 `src/word2md/docx_features.py`
- `markdown_formatter.py`
  - 历史模块，后续建议只改 `src/word2md/markdown_formatter.py`
- `pipeline.py`
  - 历史模块，后续建议只改 `src/word2md/pipeline.py`
- `word_processing.py`
  - 历史模块，后续建议只改 `src/word2md/word_processing.py`

## 这个子项目负责什么

- 读取原始 `doc/docx/pdf` 合同、第三方审查结果、最终审查意见、采纳说明
- 输出结构稳定的 `output.md`
- 同步输出 `meta.json`，保留源文件路径、批注锚点、样式提示、`.doc -> .docx` 转换信息
- PDF 默认走 `pypdf` / `PyPDF2` 的本地解析链路，不再依赖 Docling 模型下载
- 这种方案更适合公司电脑和客户电脑，通常不需要管理员权限，也不依赖 HuggingFace 缓存
- 当前 PDF 解析重点是“稳定可用”，能保留分页和基础文本结构，但标题层级、表格还原能力弱于模型方案
- 每次批量运行输出 `run_summary.json`

## 默认输入输出

- 默认输入目录：`data/合同数据-2026.3.12`
- 默认输出根目录：`data/contract_review_outputs/word2md`
- 单次跑批目录结构：`data/contract_review_outputs/word2md/<batch_name>/<合同相对路径>/`

## 环境

```powershell
conda activate langchain
```

如当前环境缺少 `docling`：

```powershell
pip install docling
```

如需处理 `pdf`，还需要安装轻量解析依赖：

```powershell
pip install pypdf
```

## 常用命令

### 推荐入口

```powershell
conda activate langchain
python Contract_Review_System/word2md/scripts/main.py `
  --input data/合同数据-2026.3.12 `
  --recursive `
  --output contract_md_260323
```

### 兼容旧入口

```powershell
conda activate langchain
python Contract_Review_System/word2md/main.py `
  --input data/合同数据-2026.3.12 `
  --recursive `
  --output contract_md_260323
```

### 只处理单个文件

```powershell
conda activate langchain
python Contract_Review_System/word2md/scripts/main.py `
  --input "data/合同数据-2026.3.12/3-保密协议/2-第三方平台审查结果：保密协议.doc" `
  --output debug_single
```

## 主要参数

- `--input`：统一输入参数。可传单个 `doc/docx/pdf` 文件，也可传输入目录
- `--output`：统一输出参数，表示本次转换批次名
- `--recursive`：目录模式下递归扫描子目录
- `--output-dir`：输出根目录
- `--history-output-dir`：历史输出根目录，可复用旧 `_converted/*.docx`
- `--device`：Docling 推理设备，默认 `cpu`
- `--no-postprocess`：关闭 Markdown 后处理

兼容旧参数：`--input-file`、`--input-dir`、`--run-id`

## 关键产物说明

- `output.md`：下游统一消费的 Markdown 结果
- `meta.json`：转换元信息、批注锚点、样式提示、异常记录
- `_converted/`：原始 `.doc` 的缓存转换结果
- `_docling_input/`：给 Docling 的预处理文件
- `run_summary.json`：本次批量任务摘要
