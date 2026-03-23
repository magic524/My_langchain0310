from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
METRICS_V2_ROOT = CURRENT_FILE.parents[1]
SRC_ROOT = METRICS_V2_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.word_comment_export import export_local_llm_comment_docs  # noqa: E402


DEFAULT_DATASET = (
    CURRENT_FILE.parent
    / "outputs_fix2"
    / "20260317_word2md_eval_third_party_fix2_20260318"
    / "dataset_with_local_llm.json"
)
DEFAULT_OUTPUT_DIR = (
    CURRENT_FILE.parent
    / "outputs_fix2"
    / "20260317_word2md_eval_third_party_fix2_20260318"
    / "原合同批注版_local_llm"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="将本地模型风险点写回原合同，生成 Word 批注版。")
    parser.add_argument("--dataset-path", default=str(DEFAULT_DATASET), help="`dataset_with_local_llm.json` 路径。")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="批注版输出目录。")
    args = parser.parse_args()

    summary = export_local_llm_comment_docs(
        dataset_path=Path(args.dataset_path).resolve(),
        output_dir=Path(args.output_dir).resolve(),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
