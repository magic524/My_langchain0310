# word2md

`word2md` 是 `v2` 合同审查系统里的独立 Word 转 Markdown 子项目。

目标只有两个：

1. 把 `.doc/.docx` 合同稳定转换成更适合大模型阅读的 `Markdown`
2. 同步输出便于后续评价和追踪问题的 `meta.json` / `run_summary.json`

这套代码已经把 `Contract_Review_System/datatype_test` 里验证过的修复策略完整迁移进来，不依赖旧脚本调用；在 `2026-03-17` 的对比验证中，新项目输出与旧版
`datatype_test/outputs_md/20260317_full_eval_fixscan_v5`
的 `19` 个 `output.md` 文件完全一致，差异数为 `0`。

## 目录结构

```text
word2md/
├─ common.py               # 公共配置、路径解析、输入文件收集
├─ word_processing.py      # .doc 转 .docx、历史缓存复用、Docling 前预处理
├─ docx_features.py        # 提取批注锚点、样式提示、原始段落
├─ markdown_formatter.py   # Markdown 后处理、缺失条款修复、批注/样式注入
├─ pipeline.py             # 单文件与批量处理主流程
├─ main.py                 # 命令行入口
├─ README.md               # 使用说明
└─ CHANGELOG.md            # 变更记录
```

## 输出内容

每个 Word 文件默认会输出到：

`Contract_Review_System/v2/word2md/outputs_md/<run_id>/<相对路径>/`

其中包含：

- `output.md`：给 AI 使用的 Markdown 结果
- `meta.json`：单文件处理过程、批注注入统计、异常信息
- `_converted/`：`.doc` 转 `.docx` 时的中间文件
- `_docling_input/`：给 Docling 使用的预处理 `.docx`

每次批量运行还会额外输出：

- `run_summary.json`：本次批处理总体汇总

## 已整合的关键修复

- 兼容伪装成 `.doc` 的 `docx package`
- 兼容 `mc:AlternateContent`，避免 Docling 在部分文件上崩溃
- 支持复用历史跑批的 `_converted/*.docx` 作为兜底缓存
- 支持提取表格、相邻段落场景下的批注锚点
- 支持按条款号优先匹配批注，减少 `5.2` 挂到 `5.1` 之类的错位
- 支持按原始 Word 段落补回 Docling 漏掉的编号条款

## 运行环境

建议沿用你现在的环境：

```powershell
conda activate langchain
```

如果当前环境里还没有 `docling`，先安装一次：

```powershell
pip install docling
```

说明：

- 处理 `.docx` 主要依赖 `docling`
- 处理老式 `.doc` 时会优先尝试本机能力转换
- 如果某些 `.doc` 当前环境无法直接打开，会自动尝试复用历史输出目录中的 `_converted/*.docx`

## 常用命令

以下命令都在仓库根目录执行：

### 1. 按默认配置全量处理

默认输入目录：

`data/合同数据-2026.3.12`

默认输出目录：

`Contract_Review_System/v2/word2md/outputs_md`

```powershell
conda activate langchain
python Contract_Review_System/v2/word2md/main.py --input-dir data/合同数据-2026.3.12 --recursive
```

### 2. 指定本次输出批次名

```powershell
conda activate langchain
python Contract_Review_System/v2/word2md/main.py --input-dir data/合同数据-2026.3.12 --recursive --run-id 20260317_word2md_eval
```

### 3. 只处理单个文件

```powershell
conda activate langchain
python Contract_Review_System/v2/word2md/main.py --input-file "data/合同数据-2026.3.12/3-保密协议/2-第三方平台审查结果/批注版_保密协议.doc" --run-id debug_single
```

### 4. 自定义输出目录

```powershell
conda activate langchain
python Contract_Review_System/v2/word2md/main.py --input-dir data/合同数据-2026.3.12 --recursive --output-dir Contract_Review_System/v2/word2md/my_outputs --run-id my_run
```

### 5. 显式指定历史缓存目录

适合你后续迁移到新合同目录，或者想复用某次旧跑批里的 `_converted/*.docx`：

```powershell
conda activate langchain
python Contract_Review_System/v2/word2md/main.py --input-dir data/合同数据-2026.3.12 --recursive --history-output-dir Contract_Review_System/v2/word2md/outputs_md --history-output-dir Contract_Review_System/datatype_test/outputs_md --run-id my_run
```

### 6. 关闭 Markdown 后处理

一般不建议关闭，只有你想排查 Docling 原始输出时再用：

```powershell
conda activate langchain
python Contract_Review_System/v2/word2md/main.py --input-file "data/xxx.docx" --no-postprocess --run-id raw_debug
```

## 命令行参数

- `--input-file`：单个 `.doc/.docx` 文件
- `--input-dir`：批量处理目录
- `--recursive`：递归扫描子目录
- `--output-dir`：输出根目录
- `--history-output-dir`：历史输出根目录，可重复传入多个
- `--run-id`：本次批次名；不传则自动按时间生成
- `--device`：Docling 推理设备，默认 `cpu`
- `--no-postprocess`：关闭 Markdown 后处理

## 默认策略说明

如果你只执行最常用的默认命令，程序会自动做这些事：

- 读取 `data/合同数据-2026.3.12`
- 输出到 `Contract_Review_System/v2/word2md/outputs_md`
- 自动把当前输出目录加入历史缓存搜索范围
- 自动把 `Contract_Review_System/datatype_test/outputs_md` 加入历史缓存搜索范围

这意味着新项目本身是独立的，但为了兼容历史上已经成功转换过的 `.doc`，默认会把旧跑批目录当作“可选缓存源”，而不是调用旧脚本。

## 建议维护方式

后续如果你继续改 `word2md`，建议保持这两个动作同步：

1. 行为变更写入 [CHANGELOG.md](/e:/Magic_wu_python/Contract_Review_System/My_langchain0310/Contract_Review_System/v2/word2md/CHANGELOG.md)
2. 如果命令、参数、默认目录有变化，同步更新本 README

## 当前验证结论

对比批次：

- 新项目：`Contract_Review_System/v2/word2md/outputs_md/20260317_word2md_full_compare_v4`
- 旧项目：`Contract_Review_System/datatype_test/outputs_md/20260317_full_eval_fixscan_v5`

结果：

- `output.md` 文件数：`19 vs 19`
- 差异数：`0`
- 说明：新 `word2md` 当前输出已与旧 `v5` 对齐
