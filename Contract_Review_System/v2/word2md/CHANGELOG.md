# Changelog

## 2026-03-17

### 初始化 `word2md` 独立项目

- 从 `Contract_Review_System/datatype_test` 中抽离 Word 转 Markdown 核心能力
- 重构为 `common.py / word_processing.py / docx_features.py / markdown_formatter.py / pipeline.py / main.py`
- 保持独立运行，不调用旧版 `convert_md.py`

### 已迁移并保留的关键修复

- 增加 `.doc` 真实格式识别，兼容“扩展名是 `.doc`、实际内容是 `docx package`”的文件
- 增加 `mc:AlternateContent` 扁平化处理，修复部分 `.docx` 在 Docling 中报错的问题
- 增加历史 `_converted/*.docx` 兜底复用，提升老式 `.doc` 的稳定性
- 增强批注锚点提取，兼容表格、相邻段落、多锚点等场景
- 增强样式提取，保留斜体、下划线、高亮、颜色等提示信息
- 增加条款编号优先匹配，降低批注挂错段落的概率
- 增加缺失编号条款修复，补回 Docling 漏掉的原始 Word 条款

### 验证结果

- 使用 `20260317_word2md_full_compare_v4` 全量重跑
- 与 `datatype_test/outputs_md/20260317_full_eval_fixscan_v5` 对比
- `19` 个 `output.md` 全部一致，差异数为 `0`

### 后续维护约定

- 每次修复转换逻辑后，在本文件追加一条日期记录
- 如果命令、默认路径、参数有变化，同时更新 `README.md`
- 如果输出行为发生变化，建议保留一次和基准版本的对比说明
