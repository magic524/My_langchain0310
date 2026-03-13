#!/usr/bin/env python3
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import importlib.util
import json
import zipfile
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_review_v1.metrics import evaluate_participant
from contract_review_v1.reporting import dump_json_detail, participant_to_dict, render_markdown_report
from contract_review_v1.runner import parse_review_text
from contract_review_v1.schema import ParsedReview, load_dataset


def load_contract_module(module_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("contract_review_agent", str(module_path))
    if spec is None or spec.loader is None:
        msg = f"Cannot import module from {module_path}"
        raise RuntimeError(msg)

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def is_temp_word_file(path: Path) -> bool:
    return path.name.startswith("~$")


def next_run_dir(outputs_root: Path) -> Path:
    outputs_root.mkdir(parents=True, exist_ok=True)
    existing = [path.name for path in outputs_root.iterdir() if path.is_dir() and path.name.startswith("run")]
    numbers: list[int] = []
    for name in existing:
        suffix = name[3:]
        if suffix.isdigit():
            numbers.append(int(suffix))
    run_number = (max(numbers) + 1) if numbers else 1
    run_dir = outputs_root / f"run{run_number}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def find_contract_dir(input_root: Path, prefix: str) -> Path:
    for path in sorted(input_root.iterdir()):
        if path.is_dir() and path.name.startswith(prefix):
            return path
    msg = f"Cannot find contract dir with prefix {prefix} under {input_root}"
    raise FileNotFoundError(msg)


def find_original_contract_file(contract_dir: Path) -> Path:
    candidates = [
        path
        for path in contract_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".doc", ".docx"}
        and path.name.startswith("1-原合同")
        and not is_temp_word_file(path)
    ]
    if not candidates:
        msg = f"Cannot find original contract file under {contract_dir}"
        raise FileNotFoundError(msg)
    return sorted(candidates)[0]


def parse_knowledge_dir_safe(contract_module: Any, knowledge_dir: Path) -> tuple[list[Any], list[str]]:
    parsed_files: list[Any] = []
    skipped_files: list[str] = []

    for path in contract_module.iter_word_files(knowledge_dir):
        if is_temp_word_file(path):
            skipped_files.append(f"{path} (temporary lock file)")
            continue

        role = contract_module.infer_file_role(path, knowledge_dir)
        try:
            parsed = contract_module.parse_word_file(path, role)
            parsed_files.append(parsed)
        except contract_module.DocExtractionUnavailableError:
            skipped_files.append(f"{path} (legacy doc extractor unavailable)")
        except zipfile.BadZipFile:
            skipped_files.append(f"{path} (invalid docx zip structure)")
        except Exception as exc:  # noqa: BLE001
            skipped_files.append(f"{path} ({exc})")

    return parsed_files, skipped_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Formal review runner with run1/run2 output folders")
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
        "--knowledge-prefixes",
        nargs="+",
        default=["2-", "3-"],
        help="Prefixes of knowledge contract folders",
    )
    parser.add_argument(
        "--output-root",
        default=str(Path("Contract_Review_System") / "v1" / "outputs" / "formal_runs"),
        help="Root output directory for run1/run2/...",
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
        default=str(Path("Contract_Review_System") / "v1" / "data" / "real_eval_dataset.json"),
        help="Evaluation dataset JSON used to compare with third-party/final-applied/human truth",
    )
    parser.add_argument(
        "--all-paragraphs",
        action="store_true",
        help="Review all non-empty paragraphs in the target contract",
    )
    return parser.parse_args()


def build_prediction_by_clause(paragraphs: list[str], review_sections: list[tuple[str, str, Any]]) -> dict[str, ParsedReview]:
    review_map: dict[str, str] = {paragraph: review_text for paragraph, review_text, _ in review_sections}
    prediction_map: dict[str, ParsedReview] = {}
    for paragraph in paragraphs:
        review_text = review_map.get(paragraph, "无需批注")
        prediction_map[paragraph] = parse_review_text(review_text)
    return prediction_map


def maybe_write_evaluation_outputs(
    *,
    args: argparse.Namespace,
    run_dir: Path,
    test_dir_name: str,
    target_paragraphs: list[str],
    review_sections: list[tuple[str, str, Any]],
) -> dict[str, Any]:
    dataset_path = (CURRENT_DIR.parent.parent.parent / args.eval_dataset).resolve()
    if not dataset_path.exists():
        return {
            "evaluation_generated": False,
            "reason": f"eval dataset not found: {dataset_path}",
        }

    records = load_dataset(dataset_path)
    test_records = [record for record in records if record.contract_id == test_dir_name]
    if not test_records:
        return {
            "evaluation_generated": False,
            "reason": f"no records matched contract_id={test_dir_name}",
            "eval_dataset": str(dataset_path),
        }

    prediction_by_clause = build_prediction_by_clause(target_paragraphs, review_sections)
    system_predictions: list[ParsedReview] = []
    unmatched_records = 0
    for record in test_records:
        prediction = prediction_by_clause.get(record.clause_text)
        if prediction is None:
            unmatched_records += 1
            prediction = ParsedReview(
                has_risk=False,
                risk_level=None,
                risk_points=[],
                explanation="",
                suggestion="",
                raw_text="(该条款未进入本次审查批次，按无需批注记为未命中)",
            )
        system_predictions.append(prediction)

    third_party_predictions = [record.third_party for record in test_records]
    final_applied_predictions = [record.final_applied for record in test_records]
    participants = [
        evaluate_participant("第三方平台", test_records, third_party_predictions),
        evaluate_participant("最终应用版", test_records, final_applied_predictions),
        evaluate_participant("本系统 v1", test_records, system_predictions),
    ]

    eval_md_path = run_dir / "evaluation_metrics.md"
    eval_json_path = run_dir / "evaluation_metrics.json"

    eval_md_path.write_text(render_markdown_report(participants), encoding="utf-8")
    dump_json_detail(
        eval_json_path,
        {
            "eval_dataset": str(dataset_path),
            "contract_id": test_dir_name,
            "records_total": len(test_records),
            "records_unmatched_by_clause_text": unmatched_records,
            "participants": [participant_to_dict(item) for item in participants],
        },
    )

    return {
        "evaluation_generated": True,
        "eval_dataset": str(dataset_path),
        "eval_records": len(test_records),
        "eval_unmatched_records": unmatched_records,
        "output_evaluation_md": str(eval_md_path),
        "output_evaluation_json": str(eval_json_path),
    }


def main() -> None:
    args = parse_args()
    workspace_root = CURRENT_DIR.parent.parent.parent
    data_root = (workspace_root / args.data_root).resolve()
    output_root = (workspace_root / args.output_root).resolve()

    contract_module_path = workspace_root / "examples" / "Docs-by-LangChain" / "contract_review_agent.py"
    contract_module = load_contract_module(contract_module_path)

    test_dir = find_contract_dir(data_root, args.test_prefix)
    knowledge_dirs = [find_contract_dir(data_root, prefix) for prefix in args.knowledge_prefixes]
    test_file = find_original_contract_file(test_dir)

    run_dir = next_run_dir(output_root)
    review_md_path = run_dir / "review_report.md"
    run_meta_path = run_dir / "run_meta.json"

    runtime_config = contract_module.configure_runtime_env()

    all_knowledge_files: list[Any] = []
    skipped_legacy: list[str] = []
    for knowledge_dir in knowledge_dirs:
        parsed_files, skipped_files = parse_knowledge_dir_safe(contract_module, knowledge_dir)
        all_knowledge_files.extend(parsed_files)
        skipped_legacy.extend(skipped_files)

    if not all_knowledge_files:
        msg = "No parsed knowledge files were loaded from knowledge directories"
        raise RuntimeError(msg)

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
    for paragraph in target_paragraphs:
        references = contract_module.retrieve_references(paragraph, knowledge_documents, top_k=args.top_k)
        if not references:
            continue
        review_text = contract_module.review_single_paragraph(model, paragraph, references)
        if review_text.strip().startswith("无需批注"):
            continue
        review_sections.append((paragraph, review_text, references))

    report = contract_module.build_report(target_file, review_sections, all_knowledge_files)
    review_md_path.write_text(report, encoding="utf-8")

    eval_meta = maybe_write_evaluation_outputs(
        args=args,
        run_dir=run_dir,
        test_dir_name=test_dir.name,
        target_paragraphs=target_paragraphs,
        review_sections=review_sections,
    )

    run_meta = {
        "run_dir": str(run_dir),
        "test_contract_dir": str(test_dir),
        "test_file": str(test_file),
        "knowledge_dirs": [str(path) for path in knowledge_dirs],
        "knowledge_files_loaded": len(all_knowledge_files),
        "knowledge_documents": len(knowledge_documents),
        "skipped_legacy_doc": skipped_legacy,
        "reviewed_paragraphs": len(target_paragraphs),
        "generated_review_items": len(review_sections),
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
    run_meta_path.write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Run folder: {run_dir}")
    print(f"Review report: {review_md_path}")
    print(f"Run meta: {run_meta_path}")
    if eval_meta.get("evaluation_generated"):
        print(f"Evaluation markdown: {eval_meta.get('output_evaluation_md')}")
        print(f"Evaluation json: {eval_meta.get('output_evaluation_json')}")
    else:
        print(f"Evaluation skipped: {eval_meta.get('reason')}")


if __name__ == "__main__":
    main()
