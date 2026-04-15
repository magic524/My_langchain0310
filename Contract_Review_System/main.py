"""Contract_Review_System package entrypoint.

This thin launcher keeps the canonical project entry at the package root
while delegating the actual GUI startup to `Contract_Review_System.gui.main`.
"""

from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    """Run the default Contract_Review_System launcher."""

    from Contract_Review_System.gui.main import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())