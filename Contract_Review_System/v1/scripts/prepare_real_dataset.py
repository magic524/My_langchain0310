#!/usr/bin/env python3
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_review_v1.runner import parse_review_text


def load_module(module_path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        msg = f"Cannot import module from {module_path}"
        raise RuntimeError(msg)

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def is_temp_word_file(path: Path) -> bool:
    return path.name.startswith("~$")


def pick_file_by_prefix(files: list[Path], prefix: str) -> Path | None:
    for file in files:
        if file.name.startswith(prefix):
            return file
    return None


def pick_third_party_file(files: list[Path]) -> Path:
    filtered = [file for file in files if not is_temp_word_file(file)]
    if not filtered:
        msg = "No third-party files found"
        raise FileNotFoundError(msg)

    prioritized = [file for file in filtered if "审查意见书" in file.name]
    if prioritized:
        return sorted(prioritized)[0]

    return sorted(filtered)[0]


def extract_keywords(text: str, *, max_items: int = 6) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
    stop_words = {
        "风险级别",
        "问题说明",
        "审查批注",
        "建议修改",
        "参考依据",
        "无需批注",
        "合同",
        "条款",
        "建议",
        "修改",
    }
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in stop_words or token in seen:
            continue
        keywords.append(token)
        seen.add(token)
        if len(keywords) >= max_items:
            break
    return keywords


def structured_review_from_snippet(text: str) -> dict[str, Any]:
    compact = text.strip()
    if not compact:
        return {
            "has_risk": False,
            "risk_level": None,
            "risk_points": [],
            "explanation": "",
            "suggestion": "",
            "raw_text": "",
        }

    parsed = parse_review_text(compact)
    has_structured_fields = any(
        marker in compact for marker in ("风险级别", "问题说明", "建议修改", "审查批注")
    )
    if "无需批注" in compact:
        return asdict(parsed)
    if has_structured_fields:
        parsed.has_risk = True
        return asdict(parsed)

    risk_markers = ("风险", "争议", "违约", "责任", "赔偿", "期限", "保密", "解除")
    suggestion_markers = ("建议", "应", "应当", "补充", "明确", "删除", "调整")

    has_risk = any(marker in compact for marker in risk_markers)
    explanation = compact[:180]
    suggestion = ""
    if any(marker in compact for marker in suggestion_markers):
        suggestion = compact[:160]

    risk_points = [keyword for keyword in extract_keywords(compact, max_items=4) if len(keyword) >= 2]
    if not has_risk and not suggestion and not risk_points:
        return {
            "has_risk": False,
            "risk_level": None,
            "risk_points": [],
            "explanation": "",
            "suggestion": "",
            "raw_text": "无需批注",
        }

    return {
        "has_risk": True,
        "risk_level": parsed.risk_level,
        "risk_points": risk_points,
        "explanation": explanation,
        "suggestion": suggestion,
        "raw_text": compact,
    }


def align_review_to_clauses(
    clauses: list[str],
    source_parsed: Any,
    *,
    contract_module: Any,
) -> dict[str, str]:
    """Align review document paragraphs to contract clauses via reverse matching.

    For each review paragraph, find the contract clause it most closely discusses
    (reverse assignment), then collect results per clause. This avoids the
    structural misalignment that occurs when review documents use a numbered-list
    format that does not mirror the original contract's paragraph order.

    Args:
        clauses: All contract clause texts (deduplicated, in order).
        source_parsed: Parsed review document (third-party / final / ground-truth).
        contract_module: The ``contract_review_agent`` module, which provides
            ``build_knowledge_documents`` and ``score_document``.

    Returns:
        Mapping from clause text to the best-aligned review snippet.  Up to
        three matched review paragraphs are joined with `` | ``.  Empty string
        when no review paragraph is assigned to the clause.
    """
    from langchain_core.documents import Document  # local to avoid hard top-level dep

    if not clauses:
        return {}

    # Build light Document objects for every contract clause so that
    # score_document() can score review paragraphs *against* them.
    clause_docs = [
        Document(page_content=clause, metadata={"clause_index": i})
        for i, clause in enumerate(clauses)
    ]

    review_docs = contract_module.build_knowledge_documents([source_parsed])
    review_paragraphs = [doc for doc in review_docs if len(doc.page_content) >= 15]

    # Reverse assignment: for each review paragraph, find its best-matching clause.
    clause_to_snippets: dict[int, list[str]] = {i: [] for i in range(len(clauses))}
    for review_doc in review_paragraphs:
        best_score = 0.0
        best_idx = -1
        for i, clause_doc in enumerate(clause_docs):
            score = contract_module.score_document(review_doc.page_content, clause_doc)
            if score > best_score:
                best_score = score
                best_idx = i
        if best_idx >= 0 and best_score > 0.0:
            clause_to_snippets[best_idx].append(review_doc.page_content)

    # Merge up to 3 snippets per clause; empty string when no snippet assigned.
    return {
        clause: " | ".join(clause_to_snippets[i][:3])
        for i, clause in enumerate(clauses)
    }


def is_substantive_clause(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 24:
        return False

    low_value_markers = (
        "统一社会信用代码",
        "身份证号",
        "联系方式",
        "联系地址",
        "以下简称",
    )
    if any(marker in compact for marker in low_value_markers):
        return False

    risk_related_markers = (
        "付款",
        "期限",
        "违约",
        "责任",
        "赔偿",
        "解除",
        "终止",
        "争议",
        "管辖",
        "保密",
        "验收",
        "不可抗力",
        "知识产权",
        "独家",
        "合作期",
        "费用",
        "发票",
    )
    if any(marker in compact for marker in risk_related_markers):
        return True

    has_clause_number = bool(re.search(r"^([一二三四五六七八九十]+[、.])|(\d+[、.])", compact))
    return has_clause_number and len(compact) >= 40


def build_contract_payload(
    contract_dir: Path,
    *,
    contract_module: Any,
    max_paragraphs: int,
    min_chars: int,
    keep_all_clauses: bool,
    all_paragraphs: bool,
) -> dict[str, Any]:
    all_files = [
        file
        for file in contract_dir.rglob("*")
        if file.is_file() and file.suffix.lower() in {".doc", ".docx"} and not is_temp_word_file(file)
    ]

    original_file = pick_file_by_prefix(all_files, "1-原合同")
    final_review_file = pick_file_by_prefix(all_files, "3-最终审查意见")
    adoption_file = pick_file_by_prefix(all_files, "4-采纳情况说明")

    third_party_candidates = [file for file in all_files if "2-第三方平台审查结果" in str(file)]
    third_party_file = pick_third_party_file(third_party_candidates)

    if original_file is None or final_review_file is None or adoption_file is None:
        msg = f"Missing required files in {contract_dir}"
        raise FileNotFoundError(msg)

    original_parsed = contract_module.parse_word_file(original_file.resolve(), role="original")
    final_review_parsed = contract_module.parse_word_file(final_review_file.resolve(), role="review")
    adoption_parsed = contract_module.parse_word_file(adoption_file.resolve(), role="review")
    third_party_parsed = contract_module.parse_word_file(third_party_file.resolve(), role="review")

    if all_paragraphs:
        all_clauses = []
        seen: set[str] = set()
        for paragraph in original_parsed.paragraphs:
            compact = contract_module.normalize_whitespace(paragraph)
            if not compact or compact in seen:
                continue
            all_clauses.append(compact)
            seen.add(compact)
        clauses = list(all_clauses)
        filtered_out = []
    else:
        all_clauses = contract_module.select_target_paragraphs(
            original_parsed,
            max_paragraphs=max(max_paragraphs * 3, 30),
            min_chars=min_chars,
        )
        if keep_all_clauses:
            clauses = all_clauses[:max_paragraphs]
            filtered_out = []
        else:
            clauses = [clause for clause in all_clauses if is_substantive_clause(clause)][:max_paragraphs]
            clause_set = set(clauses)
            filtered_out = [clause for clause in all_clauses if clause not in clause_set]

    # Precompute reverse-aligned snippet maps once per review document so that
    # each review paragraph is assigned to the clause it most closely discusses,
    # rather than naively fetching the best forward-match per clause.
    third_party_map = align_review_to_clauses(clauses, third_party_parsed, contract_module=contract_module)
    final_map = align_review_to_clauses(clauses, final_review_parsed, contract_module=contract_module)
    adoption_map = align_review_to_clauses(clauses, adoption_parsed, contract_module=contract_module)

    clause_payloads: list[dict[str, Any]] = []
    for index, clause_text in enumerate(clauses, start=1):
        third_party_snippet = third_party_map.get(clause_text, "")
        final_snippet = final_map.get(clause_text, "")
        adoption_snippet = adoption_map.get(clause_text, "")

        ground_truth = structured_review_from_snippet(adoption_snippet)
        third_party = structured_review_from_snippet(third_party_snippet)
        final_applied = structured_review_from_snippet(final_snippet)

        explanation_keywords = extract_keywords(
            f"{ground_truth.get('explanation', '')} {' '.join(ground_truth.get('risk_points', []))}",
            max_items=8,
        )
        suggestion_keywords = extract_keywords(str(ground_truth.get("suggestion", "")), max_items=8)

        clause_payloads.append(
            {
                "clause_id": f"{contract_dir.name}_c{index:03d}",
                "clause_text": clause_text,
                "ground_truth": ground_truth,
                "third_party": third_party,
                "final_applied": final_applied,
                "explanation_keywords": explanation_keywords,
                "suggestion_keywords": suggestion_keywords,
            }
        )

    return {
        "contract_id": contract_dir.name,
        "source_files": {
            "original": str(original_file),
            "third_party": str(third_party_file),
            "final_applied": str(final_review_file),
            "ground_truth": str(adoption_file),
        },
        "conversion_trace": {
            "keep_all_clauses": keep_all_clauses,
            "all_paragraphs": all_paragraphs,
            "alignment_method": "semantic_reverse",
            "candidate_clause_count": len(all_clauses),
            "selected_clause_count": len(clause_payloads),
            "filtered_out_preview": filtered_out[:20],
        },
        "clauses": clause_payloads,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare v1 evaluation dataset from real contracts")
    parser.add_argument(
        "--input-root",
        default=str(Path("data") / "合同数据-2026.3.12"),
        help="Root directory containing real contract folders",
    )
    parser.add_argument(
        "--output",
        default=str(Path("Contract_Review_System") / "v1" / "data" / "real_eval_dataset.json"),
        help="Output dataset JSON path",
    )
    parser.add_argument(
        "--max-paragraphs",
        type=int,
        default=20,
        help="Max selected clauses per contract",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=30,
        help="Minimum characters for selected clause",
    )
    parser.add_argument(
        "--keep-all-clauses",
        action="store_true",
        help="Keep clauses without heuristic filtering to avoid missing information",
    )
    parser.add_argument(
        "--all-paragraphs",
        action="store_true",
        help="Use all non-empty paragraphs from the original contract for dataset generation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace_root = CURRENT_DIR.parent.parent.parent

    contract_module_path = workspace_root / "examples" / "Docs-by-LangChain" / "contract_review_agent.py"
    contract_module = load_module(contract_module_path, "contract_review_agent_for_dataset")

    input_root = (workspace_root / args.input_root).resolve()
    output_path = (workspace_root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    contract_dirs = sorted(path for path in input_root.iterdir() if path.is_dir())
    contracts: list[dict[str, Any]] = []
    skipped: list[str] = []

    for contract_dir in contract_dirs:
        try:
            payload = build_contract_payload(
                contract_dir,
                contract_module=contract_module,
                max_paragraphs=args.max_paragraphs,
                min_chars=args.min_chars,
                keep_all_clauses=args.keep_all_clauses,
                all_paragraphs=args.all_paragraphs,
            )
            contracts.append(payload)
            print(f"Prepared: {contract_dir.name} -> {len(payload['clauses'])} clauses")
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{contract_dir}: {exc}")
            print(f"Skipped: {contract_dir.name} ({exc})")

    dataset = {
        "meta": {
            "input_root": str(input_root),
            "contracts": len(contracts),
            "skipped": len(skipped),
        },
        "contracts": contracts,
        "skipped": skipped,
    }
    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Dataset written: {output_path}")
    if skipped:
        print("Skipped details:")
        for item in skipped:
            print(f"- {item}")


if __name__ == "__main__":
    main()
