# 实验日志 — 合同文档格式保真测试 (datatype_test)

记录每次 `convert.py` 运行的情况、发现与下一步计划，用于追踪决策过程，防止黑盒。

---

## 日志格式说明

每条记录包含：

| 字段 | 说明 |
|------|------|
| **Run ID** | 自动生成（`YYYYMMDD_HHMMSS`），对应 `outputs/{run_id}/` |
| **命令** | 实际执行的完整命令 |
| **样本** | 本次涉及的样本 ID |
| **参数** | 转换参数（格式、加速器等） |
| **结果摘要** | 每种格式的成功/失败状态 |
| **发现** | 表格/标题/批注/文本完整度的观察结论 |
| **限制与问题** | 未能保留的内容、报错信息、疑问 |
| **下一步** | 基于本次结果的改进方向 |

---

## 运行记录

<!-- ─── 以下内容由每次实验手工追加 ─────────────────────────────────────────── -->

### [已完成] Run 001 — 首轮全量测试

- **Run ID**：`20260314_130551`
- **日期**：2026-03-14
- **命令**：
  ```powershell
  conda activate langchain
  cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test
  python convert.py
  ```
- **样本**：`1-brand-venue`、`2-service`、`3-nda`
- **转换参数**：默认（`--formats md html json`，`--device cpu`）
- **结果摘要**：
  - `1-brand-venue`：✅ md / ✅ html / ✅ json
  - `2-service`：✅ md / ✅ html / ✅ json
  - `3-nda`（.doc 转换链）：❌ 转换失败，原因：`soffice` 不可用，且本机缺少可用的 Win32com/Word COM 转换能力
- **表格结构保留**：
  - 待人工对照 [reports/20260314_130551_summary.md](reports/20260314_130551_summary.md) 与原文填写。
- **标题与层级保留**：
  - 待人工对照 [reports/20260314_130551_summary.md](reports/20260314_130551_summary.md) 与原文填写。
- **修订/批注保留**：
  - 待人工对照 [reports/20260314_130551_summary.md](reports/20260314_130551_summary.md) 与原文填写。
- **纯文本完整度**：
  - 待人工对照 [reports/20260314_130551_summary.md](reports/20260314_130551_summary.md) 与原文填写。
- **发现与结论**：
  - 转换主链路可用：`.docx` 样本可稳定输出 Markdown/HTML/JSON。
  - `.doc` 样本当前被系统环境阻塞，不影响脚本框架有效性，需补齐 doc 转 docx 依赖后复测。
- **限制与问题**：
  - 目前环境未安装可调用的 LibreOffice `soffice`。
  - 当前脚本使用 `comtypes` 作为 Word COM 回退通道，本机未满足该路径依赖。
- **下一步**：
  - 安装 LibreOffice 并确保 `soffice` 可执行后，复跑 `3-nda`。
  - 完成 `reports/20260314_130551_summary.md` 四维度人工勾选，形成 v2 输入格式结论。

---

<!-- ─── 后续记录在此处向下追加 ──────────────────────────────────────────────── -->

### [已完成] Run 002 — Markdown 编号纠偏修复验证

- **Run ID**：`20260314_fixcheck`
- **日期**：2026-03-14
- **命令**：
  ```powershell
  conda activate langchain
  cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test
  python convert.py --run-id 20260314_fixcheck --sample-id 1-brand-venue --formats md --device cpu
  python convert.py --run-id 20260314_130944 --sample-id 2-service --formats md --device cpu
  ```
- **修复背景**：
  - 原始 Markdown 存在两类问题：
    - 章标题编号丢失（如 `- **违约责任**` 未输出为 `**四、违约责任**`）。
    - 条款编号误判为多级嵌套（`1.` 连续缩进成树状）。
- **脚本修复点**：
  - 在 `convert.py` 新增 `postprocess_legal_markdown()`，对 Markdown 导出进行轻量纠偏：
    - 自动补齐缺失章编号；
    - 拉平误嵌套条款并顺序重排；
    - 清理异常缩进标题。
- **结果摘要**：
  - `2-service`：`**四、违约责任**` 已正确输出。
  - `1-brand-venue`：`四、双方责任与义务` 中 `（一）甲方责任与义务` 的 1-4 条已恢复为平级编号（见 fixcheck run）。
- **输出位置**：
  - [Contract_Review_System/datatype_test/outputs/20260314_fixcheck/1-brand-venue/output.md](Contract_Review_System/datatype_test/outputs/20260314_fixcheck/1-brand-venue/output.md)
  - [Contract_Review_System/datatype_test/outputs/20260314_130944/2-service/output.md](Contract_Review_System/datatype_test/outputs/20260314_130944/2-service/output.md)

---

### [已完成] Run 003 — AI 对话识别测试脚本创建

- **日期**：2026-03-14
- **目标**：新增独立脚本，验证模型能否正确、可追溯地识别 Docling 转换后的 Markdown 合同内容。
- **新增文件**：
  - `chat_md_test.py`
- **接口策略**：
  - 参考 v1 的 OpenAI 兼容接口方式（`/chat/completions` + `.env` 变量约定）。
  - 与 v1 完全独立，不调用 v1 代码。
- **脚本能力**：
  - 自动模式：两轮对话测试（结构化抽取 + 自检对话）并评分。
  - 交互模式：`--interactive` 手动追问。
  - 可审计输出：写入 `reports/*_chat_test_*.md/.json`。
- **推荐首测命令**：
  ```powershell
  conda activate langchain
  cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test
  python chat_md_test.py --run-id 20260314_fixcheck --sample-id 1-brand-venue
  ```
- **下一步**：
  - 对 `1-brand-venue`、`2-service` 分别执行自动模式并比较分数。
  - 若 `3-nda` 的 `.doc` 转换修复完成，再纳入同一对话评测链路。

---

### [已完成] Run 004 — AI 对话识别脚本首轮实测

- **Run ID（来源转换结果）**：`20260314_140033`
- **日期**：2026-03-14
- **命令**：
  ```powershell
  conda activate langchain
  cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test
  python chat_md_test.py --run-id 20260314_140033 --sample-id 1-brand-venue
  ```
- **输出文件**：
  - `reports/20260314_142804_chat_test_1-brand-venue.md`
  - `reports/20260314_142804_chat_test_1-brand-venue.json`
- **结果摘要**：
  - Turn 1（结构化抽取）评分：`67`
  - Turn 2（自检对话）评分：`100`
  - 综合评分：`84`
- **关键发现**：
  - 模型存在思维草稿泄漏（输出包含 `Thinking Process`）。
  - 存在证据引用未命中原文的问题（可追溯性不稳定）。
  - 评分规则可有效暴露“格式看似正确但证据不扎实”的情况。
- **本轮修复**：
  - `chat_md_test.py` 已增加“思维草稿泄漏检查”。
  - 增强 JSON 解析鲁棒性，兼容非法反斜杠转义。
- **下一步**：
  - 复测 `2-service`，比较不同合同类型下的证据命中率。
  - 在后续 agent 流程里加入“禁止思维草稿 + 必须原文证据”硬约束模板。

---

### [已完成] Run 005 — Markdown 专用转换脚本创建

- **日期**：2026-03-16
- **目标**：按新需求提供仅 Markdown 输出的转换脚本，支持单文件和文件夹批量输入。
- **新增文件**：
  - `convert_md.py`
- **功能覆盖**：
  - 只输出 Markdown（`output.md`）与元数据（`meta.json`），不生成 HTML/JSON/汇总报告。
  - 支持 `--input-file` 单文件输入。
  - 支持 `--input-dir` 文件夹输入，目录模式可 `--recursive` 递归。
  - 保留 `.doc -> .docx` 预处理链（LibreOffice -> Word COM）。
  - 保留有利于模型识别的导出参数（分页标记、标注导出、轻量后处理）。
- **输出结构**：
  - `outputs_md/{run_id}/{sample_id}/output.md`
  - `outputs_md/{run_id}/{sample_id}/meta.json`
  - `outputs_md/{run_id}/run_summary.json`
- **推荐命令**：
  ```powershell
  python convert_md.py --input-dir data/合同数据-2026.3.12 --recursive
  ```

---

### [已完成] Run 006 — Markdown 专用脚本冒烟测试

- **Run ID**：`md_only_smoke`
- **日期**：2026-03-16
- **命令**：
  ```powershell
  conda activate langchain
  cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test
  python convert_md.py --input-file data/合同数据-2026.3.12/2-服务协议/1-原合同-服务协议.docx --run-id md_only_smoke --device cpu
  ```
- **结果摘要**：
  - Success: 1
  - Failed: 0
- **输出位置**：
  - `outputs_md/md_only_smoke/1-原合同-服务协议/output.md`
  - `outputs_md/md_only_smoke/1-原合同-服务协议/meta.json`
  - `outputs_md/md_only_smoke/run_summary.json`

---

### [已完成] Run 007 — 路径镜像与批注锚点增强

- **Run ID**：`md_mirror_comment_test`
- **日期**：2026-03-16
- **目标**：
  - 递归模式输出目录与输入目录层级保持一致；
  - 抽取 Word 批注及其原文关联段落，供模型判定。
- **脚本改动**：
  - `convert_md.py` 目录模式改为使用输入相对路径（去扩展名）作为输出子路径。
  - 新增 `extract_docx_comments_with_anchors()`：从 `comments.xml` + `document.xml` 抽取批注与段落锚点。
  - 新增 `append_comment_section()`：将批注信息追加到 `output.md`。
  - `meta.json` 新增 `comment_anchor_count`、`comment_anchors` 字段。
- **命令**：
  ```powershell
  conda activate langchain
  cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test
  python convert_md.py --input-dir data/合同数据-2026.3.12 --recursive --run-id md_mirror_comment_test --device cpu
  ```
- **结果摘要**：
  - 总计：19
  - 成功：17
  - 失败：2（Docling pipeline 错误）
  - 多个批注版文件成功抽取到批注锚点（如 26 条、20 条、14 条等）
- **验证样例**：
  - `outputs_md/md_mirror_comment_test/1-品牌球馆冠名合作协议/2-第三方平台审查结果/Alpha GPT/修订批注版-品牌球馆冠名合作协议/output.md`
  - `outputs_md/md_mirror_comment_test/1-品牌球馆冠名合作协议/2-第三方平台审查结果/Alpha GPT/修订批注版-品牌球馆冠名合作协议/meta.json`

---

### [已完成] Run 008 — 批注就地锚注 + 样式提示注入

- **Run ID**：`inline1`
- **日期**：2026-03-16
- **目标**：
  - 批注不再尾部独立罗列，而是就地贴在对应原文段落附近，减少上下文占用。
  - 增强样式信息保真：补充颜色/高亮/下划线/斜体提示。
- **脚本改动**：
  - 删除尾部批注拼接逻辑，改为 `inject_inline_annotations()` 就地注入。
  - 新增 `extract_docx_style_hints()`，提取段落样式标签。
  - `meta.json` 增加 `style_hints` 与 `inline_injection` 匹配统计。
- **命令**：
  ```powershell
  conda activate langchain
  cd E:\Magic_wu_python\Contract_Review_System\My_langchain0310\Contract_Review_System\datatype_test
  python convert_md.py --input-file data/合同数据-2026.3.12/1-品牌球馆冠名合作协议/2-第三方平台审查结果/Alpha GPT/修订批注版-品牌球馆冠名合作协议.docx --run-id inline1 --device cpu
  ```
- **结果摘要**：
  - comment_anchor_count: 26
  - style_hint_count: 1
  - inline_injection: comment_matched=19, comment_unmatched=7, style_matched=1, style_unmatched=0
- **输出位置**：
  - `outputs_md/inline1/修订批注版-品牌球馆冠名合作协议/output.md`
  - `outputs_md/inline1/修订批注版-品牌球馆冠名合作协议/meta.json`
