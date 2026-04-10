"""Compatibility re-export for `word2md.pipeline`."""

from __future__ import annotations

import sys
from pathlib import Path


WORD2MD_ROOT = Path(__file__).resolve().parent
SRC_ROOT = WORD2MD_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from word2md.pipeline import *  # noqa: F403
