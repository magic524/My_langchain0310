# word2md 结构说明

## 推荐修改位置

- 命令入口改 `src/word2md/cli.py`
- 路径和输入收集改 `src/word2md/common.py`
- 转换主流程改 `src/word2md/pipeline.py`
- Word 预处理改 `src/word2md/word_processing.py`
- Markdown 后处理改 `src/word2md/markdown_formatter.py`
- 批注和样式提取改 `src/word2md/docx_features.py`

## 兼容原则

- `main.py` 继续保留，避免旧命令失效
- 根目录历史模块暂时保留，避免外部旧导入立刻断掉
- 后续新增逻辑优先写进 `src/word2md/`
