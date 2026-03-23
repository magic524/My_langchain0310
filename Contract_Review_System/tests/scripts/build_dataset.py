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


def main() -> None:
    """构建 tests 数据集。"""

    parser = argparse.ArgumentParser(description="Build tests dataset from word2md outputs")
    parser.add_argument("--run-id", required=True, help="word2md run id")
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

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = (
            PROJECT_ROOT
            / "Contract_Review_System"
            / "tests"
            / "outputs"
            / "datasets"
            / f"dataset_{args.run_id}.json"
        ).resolve()

    word2md_run_root = Path(args.word2md_run_dir).resolve() if args.word2md_run_dir else None
    payload = build_dataset(PROJECT_ROOT, args.run_id, output_path, word2md_run_root=word2md_run_root)
    print(f"dataset built: {output_path}")
    print(f"contracts: {len(payload.contracts)}")
    print(f"warnings: {len(payload.warnings)}")


if __name__ == "__main__":
    main()
