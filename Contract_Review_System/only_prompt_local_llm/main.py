"""Main entrypoint for `only_prompt_local_llm`.

Keep the common `main.py` entry at the project root, while delegating the
actual CLI implementation to `src/only_prompt_local_llm/cli.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path


ONLY_PROMPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ONLY_PROMPT_ROOT.parents[1]
SRC_ROOT = ONLY_PROMPT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from only_prompt_local_llm.cli import main


if __name__ == "__main__":
    main()
