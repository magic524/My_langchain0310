# web_UI

`web_UI` 是合同审查系统的 Web Demo 子模块。

当前 V0 仅提供：

- 拖拽上传单个 `doc` / `docx`
- 后台调用 `word2md`
- 页面展示本次转换的输出路径与关键产物路径

## 启动方式

```powershell
conda activate langchain
streamlit run Contract_Review_System/web_UI/app.py
```

## 当前范围

- 仅接入 `word2md`
- 不接入 `only_prompt_local_llm`
- 不展示甲乙方倾向与额外提示词
- 不做复杂结果预览
