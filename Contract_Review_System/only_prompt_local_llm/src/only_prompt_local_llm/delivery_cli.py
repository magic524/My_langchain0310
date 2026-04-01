from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from Contract_Review_System.common.local_llm_client import (
    load_runtime_config,
    resolve_runtime_env_path,
)

from .local_model_runner import run_local_prediction
from .review_report import export_review_reports
from .word_comment_export import export_local_llm_comment_docs_deliverable


CURRENT_FILE = Path(__file__).resolve()
ONLY_PROMPT_ROOT = CURRENT_FILE.parents[2]
PROJECT_ROOT = CURRENT_FILE.parents[4]


def _resolve_optional_path(path_str: str) -> Path:
    candidate = Path(path_str).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _default_output_root(run_id: str) -> Path:
    date_tag = datetime.now().strftime("%Y%m%d")
    return (ONLY_PROMPT_ROOT / "outputs" / f"{run_id}_review_bundle_{date_tag}").resolve()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the delivery-oriented local review pipeline."""

    parser = argparse.ArgumentParser(
        description="运行 only_prompt_local_llm 主流程，输出批注版合同与审查报告。"
    )
    parser.add_argument(
        "--input",
        default="",
        help="统一输入参数。可传 word2md 批次名，或直接传某次 word2md 输出目录。",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="兼容旧参数：word2md 批次名。",
    )
    parser.add_argument(
        "--word2md-run-dir",
        default="",
        help="可选，显式指定某次 word2md 输出目录。",
    )
    parser.add_argument(
        "--output",
        default="",
        help="统一输出参数。可传输出目录名，或直接传完整输出目录路径。",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="可选，显式指定本次输出目录。",
    )
    parser.add_argument(
        "--reuse-raw-responses",
        action="store_true",
        help="复用已有 raw_responses/*.txt，只重跑解析和交付物导出。",
    )
    parser.add_argument(
        "--contract-filter",
        default="",
        help="只处理 contract_id 包含指定关键字的合同。",
    )
    return parser


def main() -> None:
    """Run the delivery-oriented local review pipeline."""

    parser = build_parser()
    args = parser.parse_args()

    input_value = args.input.strip() if args.input else ""
    word2md_run_id = args.run_id.strip()
    word2md_run_root = Path(args.word2md_run_dir).resolve() if args.word2md_run_dir else None
    if input_value:
        input_path = _resolve_optional_path(input_value)
        if input_path.exists():
            word2md_run_root = input_path
            word2md_run_id = word2md_run_root.name
        else:
            word2md_run_id = input_value

    if not word2md_run_id and word2md_run_root is None:
        parser.error("必须提供 `--input`、`--run-id` 或 `--word2md-run-dir` 之一。")

    output_value = args.output.strip() if args.output else ""
    if output_value:
        raw_output_path = Path(output_value).expanduser()
        if raw_output_path.is_absolute() or raw_output_path.parent != Path("."):
            output_root = _resolve_optional_path(output_value)
        else:
            output_root = (ONLY_PROMPT_ROOT / "outputs" / output_value).resolve()
    elif args.output_dir:
        output_root = _resolve_optional_path(args.output_dir)
    else:
        output_root = _default_output_root(word2md_run_id)

    internal_root = output_root / "internal"
    deliverables_root = output_root / "deliverables"

    runtime = load_runtime_config(resolve_runtime_env_path())
    pipeline_info = run_local_prediction(
        word2md_run_id,
        runtime,
        output_dir=internal_root,
        word2md_run_root=word2md_run_root,
        reuse_raw_responses=args.reuse_raw_responses,
        contract_filter=args.contract_filter.strip() or None,
    )

    dataset_path = Path(pipeline_info["dataset_path"])
    comment_output_dir = deliverables_root / "commented_contracts"
    comment_summary = export_local_llm_comment_docs_deliverable(dataset_path, comment_output_dir)
    report_output_dir = deliverables_root / "review_reports"
    report_summary = export_review_reports(dataset_path, report_output_dir)

    summary_payload = {
        "run_id": word2md_run_id,
        "generated_at": datetime.now().isoformat(),
        "word2md_run_root": str(word2md_run_root) if word2md_run_root else "",
        "output_root": str(output_root),
        "internal_root": str(internal_root),
        "deliverables_root": str(deliverables_root),
        "dataset_from_word2md": pipeline_info["dataset_source_path"],
        "dataset_with_local_llm": pipeline_info["dataset_path"],
        "local_llm_predictions": pipeline_info["prediction_path"],
        "comment_output_dir": str(comment_output_dir),
        "comment_doc_count": len(comment_summary.get("contracts", [])),
        "report_output_dir": str(report_output_dir),
        "report_count": len(report_summary.get("contracts", [])),
        "report_summary_path": report_summary.get("summary_path", ""),
    }
    _write_json(internal_root / "pipeline_summary.json", summary_payload)

    print(f"output root: {output_root}")
    print(f"deliverables root: {deliverables_root}")
    print(f"comment docs: {comment_output_dir}")
    print(f"review reports: {report_output_dir}")


if __name__ == "__main__":
    main()
