"""Preferred script entrypoint for `word2md`."""

from __future__ import annotations

import sys
from pathlib import Path


WORD2MD_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORD2MD_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from word2md.cli import main


if __name__ == "__main__":
    main()
