# word2md

`word2md` 是合同审查系统的格式转换子项目，负责把 `doc/docx` 合同材料转换为后续评测和模型调用可直接复用的 Markdown 产物。

## 这个子项目负责什么

- 读取原始 `doc/docx` 合同、第三方审查结果、最终审查意见、采纳说明
- 输出结构稳定的 `output.md`
- 同步输出 `meta.json`，保留源文件路径、批注锚点、样式提示、`.doc -> .docx` 转换信息
- 每次批量运行输出 `run_summary.json`

## 默认输入输出

- 默认输入目录：`data/合同数据-2026.3.12`
- 默认输出根目录：`data/contract_review_outputs/word2md`
- 单次跑批目录结构：`data/contract_review_outputs/word2md/<run_id>/<合同相对路径>/`

示例：

```text
data/contract_review_outputs/word2md/20260317_word2md_eval/
├── 1-品牌球馆冠名合作协议/
│   ├── 1-原合同：品牌球馆冠名合作协议/
│   │   ├── output.md
│   │   ├── meta.json
│   │   └── _converted/
│   ├── 2-第三方平台审查结果/
│   ├── 3-最终审查意见：品牌球馆冠名合作协议/
│   └── 4-采纳情况说明-品牌球馆冠名合作协议/
└── run_summary.json
```

## 环境

```powershell
conda activate langchain
```

如当前环境缺少 `docling`：

```powershell
pip install docling
```

## 常用命令

全量转换并递归扫描：

```powershell
conda activate langchain
python Contract_Review_System/word2md/main.py --input-dir data/合同数据-2026.3.12 --recursive --run-id 20260317_word2md_eval
```

指定输出根目录：

```powershell
conda activate langchain
python Contract_Review_System/word2md/main.py --input-dir data/合同数据-2026.3.12 --recursive --output-dir data/contract_review_outputs/word2md --run-id 20260317_word2md_eval
```

只处理单个文件：

```powershell
conda activate langchain
python Contract_Review_System/word2md/main.py --input-file "data/合同数据-2026.3.12/3-保密协议/2-第三方平台审查结果/修订批注版_保密协议.doc" --run-id debug_single
```

关闭 Markdown 后处理，仅用于排查原始转换结果：

```powershell
conda activate langchain
python Contract_Review_System/word2md/main.py --input-file "data/xxx.docx" --no-postprocess --run-id raw_debug
```

## 主要参数

- `--input-file`：单个 `doc/docx` 文件
- `--input-dir`：批量输入目录
- `--recursive`：递归扫描子目录
- `--output-dir`：输出根目录
- `--history-output-dir`：额外历史输出目录，可复用旧 `_converted/*.docx`
- `--run-id`：本次跑批编号
- `--device`：Docling 推理设备，默认 `cpu`
- `--no-postprocess`：关闭 Markdown 后处理

## 关键产物说明

- `output.md`：下游统一消费的 Markdown 结果
- `meta.json`：转换元信息、批注锚点、样式提示、异常记录
- `_converted/`：原始 `.doc` 的缓存转换结果
- `_docling_input/`：给 Docling 的预处理文件
- `run_summary.json`：本次批量任务摘要

## 使用约定

- `tests` 和 `only_prompt_local_llm` 默认都从 `data/contract_review_outputs/word2md/<run_id>` 读取输入
- 如需复跑历史数据，优先保留 `run_id` 目录，不建议手工改内部层级
- 行为变更请同步更新 `CHANGELOG.md`
