from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
SRC_ROOT = CURRENT_FILE.parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_tests.dataset_builder import build_dataset


def _resolve_optional_path(path_str: str) -> Path:
    candidate = Path(path_str).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


def main() -> None:
    """构建 tests 数据集。"""

    parser = argparse.ArgumentParser(description="Build tests dataset from word2md outputs")
    parser.add_argument(
        "--input",
        default="",
        help="统一输入参数。可传 word2md 批次名，或直接传某次 word2md 输出目录。",
    )
    parser.add_argument("--run-id", default="", help="兼容旧参数：word2md run id")
    parser.add_argument(
        "--word2md-run-dir",
        default="",
        help="可选，显式指定 word2md 某次跑批目录。",
    )
    parser.add_argument(
        "--output",
        default="",
        help="可选，显式指定数据集输出路径。默认写入 Contract_Review_System/tests/outputs/datasets/。",
    )
    args = parser.parse_args()

    input_value = args.input.strip() if args.input else ""
    run_id = args.run_id.strip()
    word2md_run_root = Path(args.word2md_run_dir).resolve() if args.word2md_run_dir else None
    if input_value:
        input_path = _resolve_optional_path(input_value)
        if input_path.exists():
            word2md_run_root = input_path
            run_id = word2md_run_root.name
        else:
            run_id = input_value

    if not run_id and word2md_run_root is None:
        parser.error("必须提供 `--input`、`--run-id` 或 `--word2md-run-dir` 之一。")

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = (
            PROJECT_ROOT
            / "Contract_Review_System"
            / "tests"
            / "outputs"
            / "datasets"
            / f"dataset_{run_id}.json"
        ).resolve()

    payload = build_dataset(PROJECT_ROOT, run_id, output_path, word2md_run_root=word2md_run_root)
    print(f"dataset built: {output_path}")
    print(f"contracts: {len(payload.contracts)}")
    print(f"warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
