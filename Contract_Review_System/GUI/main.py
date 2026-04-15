"""合同审查系统 GUI 第一版入口。"""

from __future__ import annotations

import sys
from pathlib import Path


GUI_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_ROOT.parents[1]
# 直接运行 `python gui/main.py` 时，补上项目根目录，确保包内导入稳定可用。
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """启动 GUI。

    该函数只负责两件事：
    1. 延迟导入窗口模块，避免在未安装 PyQt6 时导入阶段直接崩溃。
    2. 将依赖异常转换为友好的终端报错并返回非 0 退出码。
    """

    try:
        # CRSv1 GUI 在新窗口模块中实现，入口文件只负责启动和兜底报错。
        from Contract_Review_System.gui.qt_app_crsv1 import run
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
