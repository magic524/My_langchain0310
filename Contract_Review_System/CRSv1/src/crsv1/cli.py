from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from Contract_Review_System.common.local_llm_client import load_runtime_config, resolve_runtime_env_path

from .input_adapter import resolve_optional_path
from .pipeline import CRSV1_ROOT, run_crsv1_prediction


def _default_output_root(run_id: str) -> Path:
    date_tag = datetime.now().strftime("%Y%m%d")
    return (CRSV1_ROOT / "outputs" / f"{run_id}_crsv1_{date_tag}").resolve()


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for CRSv1."""

    parser = argparse.ArgumentParser(
        description="运行 CRSv1 主流程：合同背景抽取、条款切分、多条款审查、批注导出和报告导出。"
    )
    parser.add_argument("--input", default="", help="word2md 批次名，或某次 word2md 输出目录。")
    parser.add_argument("--run-id", default="", help="兼容参数：word2md 批次名。")
    parser.add_argument("--word2md-run-dir", default="", help="显式指定 word2md 输出目录。")
    parser.add_argument("--output", default="", help="输出目录名或完整输出目录路径。")
    parser.add_argument("--output-dir", default="", help="显式指定本次输出目录。")
    parser.add_argument("--reuse-raw-responses", action="store_true", help="复用已有 raw_responses。")
    parser.add_argument("--contract-filter", default="", help="只处理 contract_id 包含指定关键字的合同。")
    parser.add_argument("--review-stance", default="", choices=["", "party_a", "party_b"], help="审查立场。")
    parser.add_argument("--extra-user-instruction", default="", help="用户补充审查要求。")
    parser.add_argument("--max-workers", default=1, type=int, help="父条款审查任务的最大并发数。")
    return parser


def main() -> None:
    """Run CRSv1 from the command line."""

    parser = build_parser()
    args = parser.parse_args()

    input_value = args.input.strip() if args.input else ""
    word2md_run_id = args.run_id.strip()
    word2md_run_root = Path(args.word2md_run_dir).resolve() if args.word2md_run_dir else None
    if input_value:
        input_path = resolve_optional_path(input_value)
        if input_path.exists():
            word2md_run_root = input_path
            word2md_run_id = input_path.name
        else:
            word2md_run_id = input_value

    if not word2md_run_id and word2md_run_root is None:
        parser.error("必须提供 `--input`、`--run-id` 或 `--word2md-run-dir` 之一。")

    output_value = args.output.strip() if args.output else ""
    if output_value:
        raw_output_path = Path(output_value).expanduser()
        if raw_output_path.is_absolute() or raw_output_path.parent != Path("."):
            output_root = resolve_optional_path(output_value)
        else:
            output_root = (CRSV1_ROOT / "outputs" / output_value).resolve()
    elif args.output_dir:
        output_root = resolve_optional_path(args.output_dir)
    else:
        output_root = _default_output_root(word2md_run_id)

    runtime = load_runtime_config(resolve_runtime_env_path())
    result = run_crsv1_prediction(
        word2md_run_id,
        runtime,
        output_dir=output_root,
        word2md_run_root=word2md_run_root,
        reuse_raw_responses=args.reuse_raw_responses,
        contract_filter=args.contract_filter.strip() or None,
        review_stance=args.review_stance or None,
        extra_user_instruction=args.extra_user_instruction.strip(),
        max_workers=max(1, int(args.max_workers)),
    )
    print(f"output root: {result['output_dir']}")
    print(f"result json: {result['result_path']}")
    print(f"comment docs: {result['comment_output_dir']}")
    print(f"report: {result['primary_report_path']}")
