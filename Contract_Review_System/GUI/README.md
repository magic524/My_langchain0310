# GUI

`Contract_Review_System/GUI` 是合同审查系统的 PyQt 第一版界面。

## 当前目标

- 输入单个原合同 `doc/docx/pdf`
- 选择审查立场：甲方 / 乙方
- 输入额外审查要求
- 调用 `contract_review_pipeline`
- 展示最终批注版 Word、审查报告与输出目录
- 左侧实时显示阶段进度与日志

## 目录建议

```text
GUI/
├─ README.md
├─ __init__.py
├─ main.py
├─ qt_app.py
├─ service.py
└─ styles.py
```

## 运行方式

```powershell
conda activate langchain
pip install PyQt6
pip install pdf2docx
python Contract_Review_System/GUI/main.py
```

## 设计约定

- `service.py` 负责封装后端流水线调用，便于单元测试
- `qt_app.py` 只负责窗口、线程、信号槽和状态展示
- 第一版先代码布局，后续可迁移到 Qt Designer
- Qt Designer 只建议接管静态布局，不承担业务逻辑
