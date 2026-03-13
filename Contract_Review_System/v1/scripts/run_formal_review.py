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
    return parser.parse_args()


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
        },
    }
    run_meta_path.write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Run folder: {run_dir}")
    print(f"Review report: {review_md_path}")
    print(f"Run meta: {run_meta_path}")


if __name__ == "__main__":
    main()
