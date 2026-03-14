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
