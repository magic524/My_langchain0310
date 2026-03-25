from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .evaluator import evaluate_dataset
from .export_parallel_reports_to_xlsx import export_markdown_to_xlsx
from .format_parallel_reports_for_client import process_markdown_dir
from .markdown_table_export import convert_markdown_file_to_html
from .parallel_review_report import (
    load_parallel_audits,
    write_contract_parallel_report,
    write_overall_summary_report,
)
from .reporter import write_reports


RISK_MARKER = "【风险点】"
EXPLANATION_MARKER = "【说明】"
SUGGESTION_MARKER = "【修改建议】"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _extract_between(text: str, start: str, end_markers: tuple[str, ...]) -> str:
    if start not in text:
        return ""
    segment = text.split(start, 1)[1]
    end_positions = [segment.find(marker) for marker in end_markers if marker in segment]
    if end_positions:
        segment = segment[: min(end_positions)]
    return re.sub(r"\s+", " ", segment).strip(" ；，。")


def _parse_anchor(anchor: dict[str, Any]) -> dict[str, str] | None:
    comment_text = _safe_text(anchor.get("comment_text", ""))
    if RISK_MARKER not in comment_text:
        return None

    title = _extract_between(comment_text, RISK_MARKER, (EXPLANATION_MARKER, SUGGESTION_MARKER))
    explanation = _extract_between(comment_text, EXPLANATION_MARKER, (SUGGESTION_MARKER,))
    suggestion = _extract_between(comment_text, SUGGESTION_MARKER, tuple())

    if not title:
        title = explanation[:30] if explanation else comment_text[:30]
    if not explanation and EXPLANATION_MARKER not in comment_text:
        explanation = comment_text

    return {
        "title": title or "风险提示",
        "explanation": explanation,
        "suggestion": suggestion,
        "clause_text": _safe_text(anchor.get("paragraph_excerpt", "")),
        "source_excerpt": comment_text,
    }


def _deduplicate_risks(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in items:
        key = "|".join(
            [
                _safe_text(item.get("title", "")).lower(),
                _safe_text(item.get("explanation", "")).lower(),
                _safe_text(item.get("suggestion", "")).lower(),
                _safe_text(item.get("clause_text", "")).lower()[:120],
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_third_party_from_meta(contract: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    source_files = contract.get("source_files") or {}
    source_md = str(source_files.get("third_party_md", "")).strip()
    if not source_md:
        return [], "third_party_md missing"

    meta_path = Path(source_md).with_name("meta.json")
    if not meta_path.exists():
        return [], f"meta.json missing: {meta_path}"

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    anchors = payload.get("comment_anchors")
    if not isinstance(anchors, list):
        return [], "comment_anchors missing"

    parsed: list[dict[str, str]] = []
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        parsed_item = _parse_anchor(anchor)
        if parsed_item is None:
            continue
        if len(parsed_item["title"]) < 2 and len(parsed_item["explanation"]) < 6:
            continue
        parsed.append(parsed_item)

    parsed = _deduplicate_risks(parsed)
    contract_id = str(contract.get("contract_id", ""))
    risks: list[dict[str, Any]] = []
    for index, item in enumerate(parsed, start=1):
        risks.append(
            {
                "risk_id": f"{contract_id}_third_party_fix_{index:03d}",
                "contract_id": contract_id,
                "title": item["title"],
                "clause_text": item["clause_text"],
                "explanation": item["explanation"],
                "suggestion": item["suggestion"],
                "source_excerpt": item["source_excerpt"],
                "status": "other",
                "status_reason": "",
                "clause_id": "",
                "match_score": 0.0,
            }
        )
    return risks, ""


def _merge_third_party_risks(
    old_risks: list[dict[str, Any]],
    new_risks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    if new_risks:
        return new_risks, "prefer_parsed_only"
    if old_risks:
        return old_risks, "fallback_old_only"
    return [], "merged(empty)"


def _file_safe_contract_id(contract_id: str) -> str:
    return contract_id.replace("/", "_").replace("\\", "_").replace(":", "：")


def _participants_from_dataset(dataset_payload: dict[str, Any]) -> list[str]:
    participant_set: set[str] = set()
    for contract in dataset_payload.get("contracts", []):
        if not isinstance(contract, dict):
            continue
        participants = contract.get("participants") or {}
        if isinstance(participants, dict):
            participant_set.update(str(name) for name in participants.keys())
    ordered = [name for name in ("third_party", "final_applied", "local_llm") if name in participant_set]
    for name in sorted(participant_set):
        if name not in ordered:
            ordered.append(name)
    return ordered


def has_local_llm_participant(dataset_path: Path) -> bool:
    payload = _load_json(dataset_path)
    participants = _participants_from_dataset(payload)
    return "local_llm" in participants


def prepare_dataset_for_evaluation(dataset_path: Path, output_dir: Path) -> Path:
    """Write a normalized dataset snapshot for test-time evaluation."""

    dataset_payload = _load_json(dataset_path)
    change_log: list[dict[str, Any]] = []

    for contract in dataset_payload.get("contracts", []):
        if not isinstance(contract, dict):
            continue
        contract_id = str(contract.get("contract_id", ""))
        participants = contract.setdefault("participants", {})
        old_risks = participants.get("third_party", [])
        old_count = len(old_risks) if isinstance(old_risks, list) else 0
        new_risks, warning = _build_third_party_from_meta(contract)
        old_list = old_risks if isinstance(old_risks, list) else []
        selected_risks, selection_reason = _merge_third_party_risks(old_list, new_risks)
        participants["third_party"] = selected_risks
        change_log.append(
            {
                "contract_id": contract_id,
                "old_count": old_count,
                "parsed_count": len(new_risks),
                "final_count": len(selected_risks),
                "selection_reason": selection_reason,
                "warning": warning,
            }
        )

    prepared_dataset_path = output_dir / "dataset_for_evaluation.json"
    _write_json(prepared_dataset_path, dataset_payload)
    _write_json(output_dir / "third_party_fix_change_log.json", {"changes": change_log})
    return prepared_dataset_path


def _write_single_contract_run_dirs(
    dataset_payload: dict[str, Any],
    *,
    output_root: Path,
    participants: list[str],
) -> list[Path]:
    run_dirs: list[Path] = []
    for contract in dataset_payload.get("contracts", []):
        if not isinstance(contract, dict):
            continue
        contract_id = str(contract.get("contract_id", "")).strip()
        if not contract_id:
            continue
        contract_dir = output_root / "contract_runs" / _file_safe_contract_id(contract_id)
        contract_dir.mkdir(parents=True, exist_ok=True)

        single_payload = {
            "meta": dict(dataset_payload.get("meta") or {}),
            "warnings": list(dataset_payload.get("warnings") or []),
            "contracts": [contract],
        }
        single_dataset_path = contract_dir / "dataset_with_local_llm.json"
        _write_json(single_dataset_path, single_payload)

        single_eval = evaluate_dataset(single_dataset_path, participants=participants)
        write_reports(contract_dir, single_eval)
        run_dirs.append(contract_dir)
    return run_dirs


def _write_parallel_reports(run_dirs: list[Path], output_dir: Path, prefix: str) -> list[Path]:
    audits = load_parallel_audits(run_dirs)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_paths: list[Path] = []
    for audit in audits:
        path = output_dir / f"{prefix}_{_file_safe_contract_id(audit.contract_id)}_三方对照.md"
        generated_paths.append(write_contract_parallel_report(path, audit))

    overall_path = output_dir / f"{prefix}_总体汇总.md"
    generated_paths.append(write_overall_summary_report(overall_path, audits))
    return generated_paths


def _export_html(markdown_files: list[Path]) -> list[Path]:
    generated: list[Path] = []
    for markdown_path in markdown_files:
        html_path = markdown_path.with_suffix(".html")
        convert_markdown_file_to_html(markdown_path, html_path)
        generated.append(html_path)
    return generated


def _export_xlsx(markdown_files: list[Path]) -> list[Path]:
    generated: list[Path] = []
    for markdown_path in markdown_files:
        xlsx_path = markdown_path.with_suffix(".xlsx")
        try:
            export_markdown_to_xlsx(markdown_path, xlsx_path)
        except RuntimeError:
            continue
        generated.append(xlsx_path)
    return generated


def _move_generated_file(source_path: Path, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_path), str(target_path))
    try:
        source_path.unlink()
    except OSError:
        pass
    return target_path


def _organize_comparison_outputs(compare_root: Path, prefix: str) -> dict[str, list[str] | str]:
    organized_paths: list[str] = []
    for markdown_path in sorted(compare_root.glob("*.md")):
        stem = markdown_path.stem
        base_name = stem
        if stem.startswith(f"{prefix}_"):
            base_name = stem[len(prefix) + 1 :]

        folder_name = "总体汇总" if base_name.endswith("_总体汇总") else base_name
        target_dir = compare_root / folder_name

        moved_markdown = _move_generated_file(markdown_path, target_dir / f"{base_name}.md")
        organized_paths.append(str(moved_markdown))

        html_path = markdown_path.with_suffix(".html")
        if html_path.exists():
            organized_paths.append(str(_move_generated_file(html_path, target_dir / f"{base_name}.html")))

        xlsx_path = markdown_path.with_suffix(".xlsx")
        if xlsx_path.exists():
            organized_paths.append(str(_move_generated_file(xlsx_path, target_dir / f"{base_name}.xlsx")))

    return {
        "compare_root": str(compare_root),
        "artifacts": organized_paths,
    }


def generate_parallel_comparison_outputs(
    dataset_path: Path,
    output_dir: Path,
    run_id: str,
    participants: list[str],
) -> dict[str, list[str] | str]:
    """Generate contract-level three-way comparison artifacts under `tests`."""

    dataset_payload = _load_json(dataset_path)
    per_contract_run_dirs = _write_single_contract_run_dirs(
        dataset_payload,
        output_root=output_dir,
        participants=participants,
    )

    compare_root = output_dir / "三方对照"
    markdown_files = _write_parallel_reports(per_contract_run_dirs, compare_root, prefix=run_id)
    markdown_files = process_markdown_dir(compare_root)
    _export_html(markdown_files)
    _export_xlsx(markdown_files)
    return _organize_comparison_outputs(compare_root, run_id)
