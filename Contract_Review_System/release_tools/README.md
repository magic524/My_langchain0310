# Release Tools

## build_portable_sample.ps1

用于基于现有 `langchain` conda 环境生成一份“目录式便携样本包”。
默认行为：
- 用 `conda-pack` 打包 `E:\conda_envs\langchain`
- 解压到样本包内的 `runtime\langchain`
- 复制最小运行代码到 `app\Contract_Review_System`
- 可选复制 `data\contract_review_runtime_cache`
- 生成双击启动脚本和 `README_FIRST_USE.txt`
- 额外输出一份 zip 压缩包，方便分发

## build_nuitka_gui.ps1

用于基于 `Nuitka` 打包当前 GUI 主入口 `Contract_Review_System/GUI/main.py`。
目标是只覆盖当前 GUI -> pipeline -> word2md -> CRSv1 这条运行链，而不是整份 conda 环境原样搬运。

默认行为：
- 使用 `E:\conda_envs\langchain\python.exe`
- 构建 `--standalone` GUI 程序
- 默认使用 `--mingw64` 作为 C 编译后端，更适合当前 Python 3.11 + Windows 打包场景
- 可通过 `-CompilerBackend zig|mingw64|msvc` 切换后端
- 显式包含 `GUI / CRSv1 / contract_review_pipeline / word2md / common`
- 显式包含当前链路里常见的动态依赖，如 `mammoth`、`pdf2docx`
- 默认不包含 `win32com/comtypes`，只有加 `-IncludeWordAutomation` 才会带入 Office 自动化依赖
- 将 `.env` 一起打进输出目录

示例：
```powershell
powershell -ExecutionPolicy Bypass -File Contract_Review_System/release_tools/build_nuitka_gui.ps1 -OutputRoot E:\Magic_wu_python
```

指定 Zig：
```powershell
powershell -ExecutionPolicy Bypass -File Contract_Review_System/release_tools/build_nuitka_gui.ps1 `
  -OutputRoot E:\Magic_wu_python `
  -CompilerBackend zig
```

如需保留 `.doc` 的 Word 自动化转换：
```powershell
powershell -ExecutionPolicy Bypass -File Contract_Review_System/release_tools/build_nuitka_gui.ps1 `
  -OutputRoot E:\Magic_wu_python `
  -IncludeWordAutomation
```

## Notes

- `.doc` 转换可能仍依赖本机 Microsoft Word 自动化。
- 现在 PDF 已改为 `pdf -> pdf2docx -> docx -> word2md`，不再走 Docling 直接解析 PDF。
- Light 分支已经移除了 `docling` 打包依赖，当前主链为 `mammoth + pdf2docx`；如果仍需继续瘦身，优先检查 `pdf2docx/fitz/win32com` 相关依赖。
