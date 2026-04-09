"""Main entrypoint for `CRSv1`.

Keep the project root `main.py` for convenient direct execution while the
actual CLI implementation lives in `src/crsv1/cli.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path


CRSV1_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CRSV1_ROOT.parents[1]
SRC_ROOT = CRSV1_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from crsv1.cli import main


if __name__ == "__main__":
    main()
