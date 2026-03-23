"""Preferred script entrypoint for `only_prompt_local_llm`."""

from __future__ import annotations

import sys
from pathlib import Path


ONLY_PROMPT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ONLY_PROMPT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from only_prompt_local_llm.cli import main


if __name__ == "__main__":
    main()
