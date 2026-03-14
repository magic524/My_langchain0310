#!/usr/bin/env python3
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import contract_review_v1.agent_core as contract_module
from contract_review_v1.runner import parse_review_text
from contract_review_v1.schema import ParsedReview
from run_formal_review import (
    find_contract_dir,
    find_original_contract_file,
    maybe_write_evaluation_outputs,
    parse_knowledge_dir_safe,
)

ABLATION_MODES = ("full", "prompt-only", "service-only", "nda-only")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ablation experiments for v1")
    parser.add_argument(
        "--data-root",
        default=str(Path("data") / "合同数据-2026.3.12"),
        help="Root directory that contains 1/2/3 contract folders",
    )
    parser.add_argument(
        "--test-prefix",
        default="1-",
        help="Prefix of test contract folder (default: 1-)",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=list(ABLATION_MODES),
        default=list(ABLATION_MODES),
        help="Ablation modes to run",
    )
    parser.add_argument(
        "--output-root",
        default=str(Path("Contract_Review_System") / "v1" / "outputs" / "ablation_runs"),
        help="Root directory for ablation outputs",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top-k references for each clause",
    )
    parser.add_argument(
        "--max-paragraphs",
        type=int,
        default=15,
        help="Max reviewed paragraphs",
    )
    parser.add_argument(
        "--min-paragraph-chars",
        type=int,
        default=30,
        help="Minimum paragraph length",
    )
    parser.add_argument(
        "--eval-dataset",
        default=str(Path("Contract_Review_System") / "v1" / "data" / "real_eval_dataset_full.json"),
        help="Evaluation dataset JSON used to compare with third-party/final-applied/human truth",
    )
    parser.add_argument(
        "--all-paragraphs",
        action="store_true",
        help="Review all non-empty paragraphs in the target contract",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip evaluation report generation for faster iteration",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=5,
        help="Print progress every N clauses (default: 5)",
    )
    return parser.parse_args()


def mode_to_knowledge_prefixes(mode: str) -> list[str]:
    if mode == "full":
        return ["2-", "3-"]
    if mode == "service-only":
        return ["2-"]
    if mode == "nda-only":
        return ["3-"]
    return []


def build_prediction_by_clause(paragraphs: list[str], review_sections: list[tuple[str, str, Any]]) -> dict[str, ParsedReview]:
    review_map: dict[str, str] = {paragraph: review_text for paragraph, review_text, _ in review_sections}
    prediction_map: dict[str, ParsedReview] = {}
    for paragraph in paragraphs:
        review_text = review_map.get(paragraph, "无需批注")
        prediction_map[paragraph] = parse_review_text(review_text)
    return prediction_map


def run_mode(
    *,
    args: argparse.Namespace,
    workspace_root: Path,
    mode: str,
    output_dir: Path,
) -> dict[str, Any]:
    run_started_at = time.perf_counter()
    data_root = (workspace_root / args.data_root).resolve()
    test_dir = find_contract_dir(data_root, args.test_prefix)
    test_file = find_original_contract_file(test_dir)

    runtime_config = contract_module.configure_runtime_env()
    mode_prefixes = mode_to_knowledge_prefixes(mode)
    knowledge_dirs = [find_contract_dir(data_root, prefix) for prefix in mode_prefixes]

    all_knowledge_files: list[Any] = []
    skipped_legacy: list[str] = []
    for knowledge_dir in knowledge_dirs:
        parsed_files, skipped_files = parse_knowledge_dir_safe(contract_module, knowledge_dir)
        all_knowledge_files.extend(parsed_files)
        skipped_legacy.extend(skipped_files)

    target_role = contract_module.infer_file_role(test_file, test_dir)
    target_file = contract_module.parse_word_file(test_file, target_role)
    if args.all_paragraphs:
        target_paragraphs = []
        seen: set[str] = set()
        for paragraph in target_file.paragraphs:
            compact = contract_module.normalize_whitespace(paragraph)
            if not compact or compact in seen:
                continue
            target_paragraphs.append(compact)
            seen.add(compact)
    else:
        target_paragraphs = contract_module.select_target_paragraphs(
            target_file,
            max_paragraphs=args.max_paragraphs,
            min_chars=args.min_paragraph_chars,
        )

    if not target_paragraphs:
        msg = "No valid target paragraphs found"
        raise RuntimeError(msg)

    print(f"[{mode}] target clauses: {len(target_paragraphs)}")
    if mode == "prompt-only" and len(target_paragraphs) >= 30:
        print(
            f"[{mode}] prompt-only will call model {len(target_paragraphs)} times sequentially; "
            "this may take a long time."
        )

    knowledge_documents = contract_module.build_knowledge_documents(all_knowledge_files)
    model = contract_module.init_chat_model(
        runtime_config.model_name,
        model_provider=runtime_config.model_provider,
        temperature=runtime_config.temperature,
        api_key=runtime_config.api_key,
        base_url=runtime_config.base_url,
        extra_body=runtime_config.extra_body,
    )

    review_sections: list[tuple[str, str, Any]] = []
    llm_call_durations: list[float] = []
    total_clauses = len(target_paragraphs)
    for index, paragraph in enumerate(target_paragraphs, start=1):
        references = contract_module.retrieve_references(paragraph, knowledge_documents, top_k=args.top_k)
        if mode != "prompt-only" and not references:
            continue

        call_started_at = time.perf_counter()
        review_text = contract_module.review_single_paragraph(model, paragraph, references)
        llm_call_durations.append(time.perf_counter() - call_started_at)

        if args.log_every > 0 and (index == 1 or index == total_clauses or index % args.log_every == 0):
            recent_avg = sum(llm_call_durations[-min(5, len(llm_call_durations)) :]) / min(5, len(llm_call_durations))
            print(
                f"[{mode}] progress {index}/{total_clauses} | "
                f"last_avg={recent_avg:.2f}s/call"
            )

        if review_text.strip().startswith("无需批注"):
            continue
        review_sections.append((paragraph, review_text, references))

    review_md_path = output_dir / "review_report.md"
    report = contract_module.build_report(target_file, review_sections, all_knowledge_files)
    review_md_path.write_text(report, encoding="utf-8")

    if args.skip_eval:
        eval_meta = {
            "evaluation_generated": False,
            "reason": "skipped by --skip-eval",
        }
    else:
        eval_meta = maybe_write_evaluation_outputs(
            args=args,
            run_dir=output_dir,
            test_dir_name=test_dir.name,
            target_paragraphs=target_paragraphs,
            review_sections=review_sections,
        )

    run_meta = {
        "mode": mode,
        "run_dir": str(output_dir),
        "test_contract_dir": str(test_dir),
        "test_file": str(test_file),
        "knowledge_mode": "none" if mode == "prompt-only" else "retrieval",
        "knowledge_dirs": [str(path) for path in knowledge_dirs],
        "knowledge_files_loaded": len(all_knowledge_files),
        "knowledge_documents": len(knowledge_documents),
        "skipped_legacy_doc": skipped_legacy,
        "reviewed_paragraphs": len(target_paragraphs),
        "generated_review_items": len(review_sections),
        "timing": {
            "total_seconds": round(time.perf_counter() - run_started_at, 3),
            "llm_calls": len(llm_call_durations),
            "llm_avg_seconds": round(sum(llm_call_durations) / len(llm_call_durations), 3)
            if llm_call_durations
            else 0.0,
            "llm_max_seconds": round(max(llm_call_durations), 3) if llm_call_durations else 0.0,
            "llm_min_seconds": round(min(llm_call_durations), 3) if llm_call_durations else 0.0,
        },
        "output_review_md": str(review_md_path),
        "model": {
            "provider": runtime_config.model_provider,
            "name": runtime_config.model_name,
            "base_url": runtime_config.base_url,
        },
        "params": {
            "top_k": args.top_k,
            "max_paragraphs": args.max_paragraphs,
            "min_paragraph_chars": args.min_paragraph_chars,
            "all_paragraphs": args.all_paragraphs,
        },
        "evaluation": eval_meta,
    }

    run_meta_path = output_dir / "run_meta.json"
    run_meta_path.write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_meta


def main() -> None:
    args = parse_args()
    workspace_root = CURRENT_DIR.parent.parent.parent
    output_root = (workspace_root / args.output_root).resolve()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_summaries: list[dict[str, Any]] = []

    for mode in args.modes:
        output_dir = output_root / mode / timestamp
        output_dir.mkdir(parents=True, exist_ok=False)
        print(f"[{mode}] output dir: {output_dir}")

        summary = run_mode(
            args=args,
            workspace_root=workspace_root,
            mode=mode,
            output_dir=output_dir,
        )
        mode_summaries.append(
            {
                "mode": mode,
                "output_dir": str(output_dir),
                "generated_review_items": summary["generated_review_items"],
                "evaluation_generated": summary["evaluation"].get("evaluation_generated", False),
            }
        )

    summary_path = output_root / f"summary_{timestamp}.json"
    summary_path.write_text(json.dumps({"timestamp": timestamp, "runs": mode_summaries}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Summary: {summary_path}")
    for item in mode_summaries:
        print(
            f"Mode={item['mode']} | output={item['output_dir']} | reviews={item['generated_review_items']} | eval={item['evaluation_generated']}"
        )


if __name__ == "__main__":
    main()
