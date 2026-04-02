"""Entrypoint for the first contract review PyQt GUI."""

from __future__ import annotations

import sys
from pathlib import Path


GUI_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Run the PyQt GUI when the dependency is available."""

    try:
        from Contract_Review_System.GUI.qt_app import run
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
