"""CLI for the production contract review pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from Contract_Review_System.common.local_llm_client import load_runtime_config, resolve_runtime_env_path
from Contract_Review_System.word2md.src.word2md.common import DEFAULT_OUTPUT_DIR, resolve_path

from .pipeline_crsv1 import run_contract_review_pipeline


CURRENT_FILE = Path(__file__).resolve()
PIPELINE_SRC_ROOT = CURRENT_FILE.parents[1]
PIPELINE_ROOT = PIPELINE_SRC_ROOT.parent.parent
DEFAULT_OUTPUT_ROOT = PIPELINE_ROOT / "outputs"


def _sanitize_run_name(value: str) -> str:
    """Convert input text into a filesystem-safe run directory name."""

    cleaned = "".join(char if char not in '<>:"/\\|?*' else "_" for char in value).strip().rstrip(".")
    return cleaned or "contract_review_run"


def _default_run_name(input_value: str) -> str:
    """Use the input filename or directory name as the default run name."""

    resolved = resolve_path(input_value)
    if resolved.is_file():
        return _sanitize_run_name(resolved.stem)
    return _sanitize_run_name(resolved.name or "contract_review_run")


def _make_unique_dir(base_dir: Path) -> Path:
    """Append `_2`, `_3`, ... when the output directory already exists."""

    if not base_dir.exists():
        return base_dir

    index = 2
    while True:
        candidate = base_dir.parent / f"{base_dir.name}_{index}"
        if not candidate.exists():
            return candidate
        index += 1


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the production review pipeline."""

    parser = argparse.ArgumentParser(
        description="输入 doc/docx/pdf，自动完成 word2md、CRSv1 审查、批注版 Word 和审查报告导出。"
    )
    parser.add_argument("--input", required=True, help="输入合同文件或目录路径。")
    parser.add_argument("--recursive", action="store_true", help="目录模式下递归扫描子目录。")
    parser.add_argument("--output", default="", help="本次流水线输出目录名。默认使用时间戳。")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="流水线输出根目录。默认写入 contract_review_pipeline/outputs。",
    )
    parser.add_argument(
        "--word2md-output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="word2md 输出根目录。默认沿用 data/contract_review_outputs/word2md。",
    )
    parser.add_argument("--device", default="cpu", help="保留兼容参数，Light 分支下默认使用 `mammoth`。")
    parser.add_argument("--reuse-raw-responses", action="store_true", help="复用已有 raw_responses。")
    parser.add_argument(
        "--review-stance",
        default="",
        choices=["", "party_a", "party_b"],
        help="审查立场，可选 `party_a` 或 `party_b`。",
    )
    parser.add_argument(
        "--extra-user-instruction",
        default="",
        help="附加审查要求，会拼接到本地模型 prompt 中。",
    )
    return parser


def main() -> None:
    """Run the production review pipeline."""

    parser = build_parser()
    args = parser.parse_args()

    runtime = load_runtime_config(resolve_runtime_env_path())
    requested_name = args.output.strip() or _default_run_name(args.input.strip())
    output_root = resolve_path(args.output_dir)
    pipeline_output_dir = _make_unique_dir(output_root / requested_name)
    run_name = pipeline_output_dir.name

    result = run_contract_review_pipeline(
        input_value=args.input.strip(),
        run_name=run_name,
        runtime=runtime,
        pipeline_output_dir=pipeline_output_dir,
        word2md_output_root=resolve_path(args.word2md_output_dir),
        recursive=args.recursive,
        device=args.device,
        reuse_raw_responses=args.reuse_raw_responses,
        review_stance=args.review_stance or None,
        extra_user_instruction=args.extra_user_instruction,
    )

    print(f"pipeline output: {result['pipeline_output_dir']}")
    print(f"local llm result: {result['local_llm_result_path']}")
    print(f"comment docs: {result['comment_output_dir']}")
    if result.get("primary_comment_file"):
        print(f"comment file: {result['primary_comment_file']}")
