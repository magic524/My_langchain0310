"""Main entrypoint for the normalized core/v1 contract review kernel."""

from __future__ import annotations

import sys
from pathlib import Path


CORE_V1_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CORE_V1_ROOT.parents[2]
SRC_ROOT = CORE_V1_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from crsv1.cli import main


if __name__ == "__main__":
    main()