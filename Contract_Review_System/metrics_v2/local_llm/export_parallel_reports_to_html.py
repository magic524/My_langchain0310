from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
METRICS_V2_ROOT = CURRENT_FILE.parents[1]
SRC_ROOT = METRICS_V2_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.markdown_table_export import (  # noqa: E402
    convert_markdown_file_to_html,
)


def main() -> None:
    """Export Markdown comparison reports to HTML table files."""

    parser = argparse.ArgumentParser(
        description="Export Markdown comparison reports to stakeholder-friendly HTML tables"
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Markdown report files to export",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional output directory. Defaults to each Markdown file's parent directory.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    generated_paths: list[Path] = []
    for item in args.inputs:
        markdown_path = Path(item).resolve()
        target_dir = output_dir or markdown_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        html_path = target_dir / f"{markdown_path.stem}.html"
        convert_markdown_file_to_html(markdown_path, html_path)
        generated_paths.append(html_path)

    for path in generated_paths:
        print(path)


if __name__ == "__main__":
    main()
