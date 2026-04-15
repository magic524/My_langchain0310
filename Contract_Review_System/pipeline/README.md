# pipeline

`Contract_Review_System/pipeline` 是合同审查系统的生产编排层，负责把 `word2md` 和 `core/v1` 串成一条自动流水线。

## 职责

- 输入单个或多个 `doc/docx/pdf`
- 自动调用 `word2md`
- 自动调用 `core/v1`
- 输出结构化 `crsv1_result.json`
- 导出批注版 Word 与审查报告

## 目录关系

- `word2md` 继续负责格式转换和元信息保留
- `core/v1` 负责背景抽取、条款树解析、多条款审查、风险组装、Word 批注和报告导出
- `pipeline` 只负责把它们串起来

## 启动方式

```powershell
conda activate CRS
python Contract_Review_System/pipeline/main.py `
  --input "data/合同审核系统解决方案_20260331_v1.docx" `
  --output demo_run
```

## 主要产物

输出目录默认位于：

`Contract_Review_System/pipeline/outputs/<run_name>/`

至少会生成：

- `crsv1_result.json`
- `审查报告.md`
- `<输入文件名>_CRSv1批注版.docx`
- `_artifacts/`

## 说明

- `run_summary.json` 和 `meta.json` 仍由 `word2md` 保留，用于溯源、复跑和 Word 批注导出
- 纯生产结果统一写到 `crsv1_result.json`
- PDF 输入会先转换为 `docx`，再进入 `word2md -> core/v1 -> Word 批注/报告` 链路
- 最终批注默认直接落在 PDF 转出的 `docx` 上，展示效果比“Markdown 重建 Word”更稳定
- 顶层默认直接展示批注版 Word 和首份审查报告，文件名自动跟随输入文件名；重名时自动编号
- 辅助文件统一收纳到 `_artifacts/`，并附带 `文件说明.md`
- 后续如果需要评测，应由 `tests` 或独立评测模块额外读取 `crsv1_result.json` 与第三方结果，再做组装