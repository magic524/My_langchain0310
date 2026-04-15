"""Main entrypoint for the contract review production pipeline."""

from __future__ import annotations

import sys
from pathlib import Path


PIPELINE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PIPELINE_ROOT / "src"
PROJECT_ROOT = PIPELINE_ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_review_pipeline.cli import main


if __name__ == "__main__":
    main()
