from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
SRC_ROOT = CURRENT_FILE.parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_tests.manual_feedback_review import write_manual_feedback_reports


def _resolve_optional_path(path_str: str) -> Path:
    candidate = Path(path_str).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


def main() -> None:
    """Generate reports for manual feedback on `local_llm` annotated contracts."""

    parser = argparse.ArgumentParser(description="Evaluate manual feedback docs exported by word2md")
    parser.add_argument(
        "--input",
        required=True,
        help="`word2md` batch directory path or run id for the manual-feedback batch.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output directory. Defaults to Contract_Review_System/tests/outputs/manual_feedback_runs/<run_id>.",
    )
    args = parser.parse_args()

    input_path = _resolve_optional_path(args.input)
    if input_path.exists():
        run_root = input_path
        run_label = run_root.name
    else:
        run_label = args.input.strip()
        run_root = (
            PROJECT_ROOT / "data" / "contract_review_outputs" / "word2md" / run_label
        ).resolve()

    if not run_root.exists():
        msg = f"Input run root does not exist: {run_root}"
        raise FileNotFoundError(msg)

    if args.output:
        output_dir = _resolve_optional_path(args.output)
    else:
        output_dir = (
            PROJECT_ROOT / "Contract_Review_System" / "tests" / "outputs" / "manual_feedback_runs" / run_label
        ).resolve()

    result = write_manual_feedback_reports(run_root, output_dir, run_label=run_label)
    print(f"run root: {result['run_root']}")
    print(f"output dir: {result['output_dir']}")
    print(f"artifacts: {len(result['artifacts'])}")


if __name__ == "__main__":
    main()
