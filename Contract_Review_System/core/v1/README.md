# core/v1

`Contract_Review_System/core/v1` 是合同审查系统当前稳定的 v1 审查内核。

它负责：

- 合同背景抽取
- 父子条款切分
- 以父条款为单位的审查任务
- 风险点组装
- Word 批注导出
- 审查报告导出

## 运行方式

```powershell
conda activate CRS
python Contract_Review_System/core/v1/main.py `
  --input 20260317_word2md_eval `
  --output demo_core_v1
```

## 目录结构

```text
core/v1/
├─ README.md
├─ main.py
├─ docs/
│  └─ structure.md
├─ src/
│  └─ crsv1/
└─ tests/
```

## 说明

- 代码包名继续沿用 `crsv1`，便于保持内部模块稳定
- 顶层目录已经收敛到 `core/v1`，不再使用旧的 `CRSv1`