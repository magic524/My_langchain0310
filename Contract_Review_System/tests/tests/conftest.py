from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

ONLY_PROMPT_SRC_ROOT = Path(__file__).resolve().parents[2] / "only_prompt_local_llm" / "src"
if str(ONLY_PROMPT_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(ONLY_PROMPT_SRC_ROOT))
