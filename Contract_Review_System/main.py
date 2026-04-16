"""Contract_Review_System package entrypoint.

This thin launcher keeps the canonical project entry at the package root
while delegating the actual GUI startup to `Contract_Review_System.gui.main`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    """Run the default Contract_Review_System launcher."""

    parser = argparse.ArgumentParser(description="Launch the Contract_Review_System GUI.")
    parser.add_argument(
        "--max-workers",
        default=0,
        type=int,
        help="CRSv1 父条款并行数；0 表示按每份合同的条款数自动设置。",
    )
    args = parser.parse_args()

    from Contract_Review_System.gui.main import main as gui_main

    max_workers = args.max_workers if args.max_workers > 0 else None
    return gui_main(max_workers=max_workers)


if __name__ == "__main__":
    raise SystemExit(main())