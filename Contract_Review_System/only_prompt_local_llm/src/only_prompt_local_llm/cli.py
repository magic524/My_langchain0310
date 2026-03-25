from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
ONLY_PROMPT_ROOT = CURRENT_FILE.parents[2]
CONTRACT_REVIEW_ROOT = CURRENT_FILE.parents[3]
PROJECT_ROOT = CURRENT_FILE.parents[4]
TESTS_ROOT = CONTRACT_REVIEW_ROOT / "tests"
SRC_ROOT = TESTS_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_tests.word_comment_export import export_local_llm_comment_docs

from Contract_Review_System.common.local_llm_client import (
    load_runtime_config,
    resolve_runtime_env_path,
)

from .local_model_runner import run_local_prediction



def _resolve_optional_path(path_str: str) -> Path:
    candidate = Path(path_str).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


RISK_MARKER = "【风险点】"
EXPLANATION_MARKER = "【说明】"
SUGGESTION_MARKER = "【修改建议】"


def _safe_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _extract_between(text: str, start: str, end_markers: tuple[str, ...]) -> str:
    if start not in text:
        return ""
    segment = text.split(start, 1)[1]
    end_positions = [segment.find(marker) for marker in end_markers if marker in segment]
    if end_positions:
        segment = segment[: min(end_positions)]
    return re.sub(r"\s+", " ", segment).strip(" ；，。】")


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
        return [], "third_party_md 缺失"

    meta_path = Path(source_md).with_name("meta.json")
    if not meta_path.exists():
        return [], f"meta.json 缺失: {meta_path}"

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    anchors = payload.get("comment_anchors")
    if not isinstance(anchors, list):
        return [], "comment_anchors 缺失"

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


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        export_markdown_to_xlsx(markdown_path, xlsx_path)
        generated.append(xlsx_path)
    return generated


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


def _move_generated_file(source_path: Path, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        target_path.unlink()
    shutil.move(str(source_path), str(target_path))
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


def _default_output_root(run_id: str) -> Path:
    date_tag = datetime.now().strftime("%Y%m%d")
    return (
        PROJECT_ROOT
        / "Contract_Review_System"
        / "only_prompt_local_llm"
        / "outputs"
        / f"{run_id}_review_bundle_{date_tag}"
    ).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 only_prompt_local_llm 主流程，生成本地模型审查整包产物。"
    )
    parser.add_argument("--run-id", default="", help="兼容旧参数：word2md 跑批编号。")
    parser.add_argument(
        "--word2md-run-dir",
        default="",
        help="可选，显式指定某次 word2md 输出目录。",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="可选，显式指定本次整包输出目录。默认写入 Contract_Review_System/only_prompt_local_llm/outputs/。",
    )
    parser.add_argument(
        "--participants",
        default="third_party,final_applied,local_llm",
        help="评测时纳入的参与方，逗号分隔。",
    )
    parser.add_argument(
        "--reuse-raw-responses",
        action="store_true",
        help="复用已有 raw_responses/*.txt，只重跑解析、评测和报告导出。",
    )
    parser.add_argument(
        "--contract-filter",
        default="",
        help="只处理 contract_id 包含此字符串的合同。",
    )
    args = parser.parse_args()

    output_root = Path(args.output_dir).resolve() if args.output_dir else _default_output_root(args.run_id)
    word2md_run_root = Path(args.word2md_run_dir).resolve() if args.word2md_run_dir else None
    runtime = load_runtime_config(resolve_runtime_env_path())

    pipeline_info = run_local_prediction(
        args.run_id,
        runtime,
        output_dir=output_root,
        word2md_run_root=word2md_run_root,
        reuse_raw_responses=args.reuse_raw_responses,
        contract_filter=args.contract_filter.strip() or None,
    )

    dataset_path = Path(pipeline_info["dataset_path"])
    comment_output_dir = output_root / "原合同批注版_local_llm"
    comment_summary = export_local_llm_comment_docs(dataset_path, comment_output_dir)

    summary_payload = {
        "run_id": args.run_id,
        "generated_at": datetime.now().isoformat(),
        "word2md_run_root": str(word2md_run_root) if word2md_run_root else "",
        "output_root": str(output_root),
        "dataset_from_word2md": pipeline_info["dataset_source_path"],
        "dataset_with_local_llm": pipeline_info["dataset_path"],
        "local_llm_predictions": pipeline_info["prediction_path"],
        "comment_output_dir": str(comment_output_dir),
        "comment_doc_count": len(comment_summary.get("contracts", [])),
    }
    _write_json(output_root / "pipeline_summary.json", summary_payload)

    print(f"output root: {output_root}")
    print(f"dataset: {pipeline_info['dataset_path']}")
    print(f"local predictions: {pipeline_info['prediction_path']}")
    print(f"comment docs: {comment_output_dir}")
    return

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
                "final_count": len(participants.get("third_party", [])),
                "selection_reason": selection_reason,
                "warning": warning,
            }
        )

    _write_json(dataset_path, dataset_payload)
    _write_json(output_root / "third_party_fix_change_log.json", {"changes": change_log})

    participants = [item.strip() for item in args.participants.split(",") if item.strip()]
    evaluation_payload = evaluate_dataset(dataset_path, participants=participants)
    report_files = write_reports(output_root, evaluation_payload)

    per_contract_run_dirs = _write_single_contract_run_dirs(
        dataset_payload,
        output_root=output_root,
        participants=participants,
    )

    compare_root = output_root / "三方对照"
    markdown_files = _write_parallel_reports(per_contract_run_dirs, compare_root, prefix=args.run_id)
    markdown_files = process_markdown_dir(compare_root)
    _export_html(markdown_files)
    _export_xlsx(markdown_files)
    compare_summary = _organize_comparison_outputs(compare_root, args.run_id)

    comment_output_dir = output_root / "原合同批注版_local_llm"
    comment_summary = export_local_llm_comment_docs(dataset_path, comment_output_dir)

    summary_payload = {
        "run_id": args.run_id,
        "generated_at": datetime.now().isoformat(),
        "word2md_run_root": str(word2md_run_root) if word2md_run_root else "",
        "output_root": str(output_root),
        "dataset_from_word2md": pipeline_info["dataset_source_path"],
        "dataset_with_local_llm": pipeline_info["dataset_path"],
        "local_llm_predictions": pipeline_info["prediction_path"],
        "evaluation_report": report_files["markdown"],
        "evaluation_json": report_files["json"],
        "comparison_outputs": compare_summary,
        "comment_output_dir": str(comment_output_dir),
        "comment_doc_count": len(comment_summary.get("contracts", [])),
    }
    _write_json(output_root / "pipeline_summary.json", summary_payload)

    print(f"output root: {output_root}")
    print(f"dataset: {pipeline_info['dataset_path']}")
    print(f"local predictions: {pipeline_info['prediction_path']}")
    print(f"evaluation report: {report_files['markdown']}")
    print(f"comparison dir: {compare_root}")
    print(f"comment docs: {comment_output_dir}")

def main() -> None:
    """Run the local-only prompt pipeline.

    This entrypoint intentionally only produces:
    - `dataset_with_local_llm.json`
    - `local_llm_predictions.json`
    - `原合同批注版_local_llm`

    Evaluation and three-way comparison artifacts are owned by `tests`.
    """

    parser = argparse.ArgumentParser(
        description="运行 only_prompt_local_llm 主流程，只生成 local_llm 结果与原合同批注版。"
    )
    parser.add_argument(
        "--input",
        default="",
        help="统一输入参数。可传 word2md 批次名，或直接传某次 word2md 输出目录。",
    )
    parser.add_argument("--run-id", default="", help="兼容旧参数：word2md 跑批编号。")
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
        help="可选，显式指定本次输出目录。默认写入 Contract_Review_System/only_prompt_local_llm/outputs/。",
    )
    parser.add_argument(
        "--reuse-raw-responses",
        action="store_true",
        help="复用已有 raw_responses/*.txt，只重跑解析和批注版导出。",
    )
    parser.add_argument(
        "--contract-filter",
        default="",
        help="只处理 contract_id 包含此字符串的合同。",
    )
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
    runtime = load_runtime_config(resolve_runtime_env_path())

    pipeline_info = run_local_prediction(
        word2md_run_id,
        runtime,
        output_dir=output_root,
        word2md_run_root=word2md_run_root,
        reuse_raw_responses=args.reuse_raw_responses,
        contract_filter=args.contract_filter.strip() or None,
    )

    dataset_path = Path(pipeline_info["dataset_path"])
    comment_output_dir = output_root / "原合同批注版_local_llm"
    comment_summary = export_local_llm_comment_docs(dataset_path, comment_output_dir)

    summary_payload = {
        "run_id": word2md_run_id,
        "generated_at": datetime.now().isoformat(),
        "word2md_run_root": str(word2md_run_root) if word2md_run_root else "",
        "output_root": str(output_root),
        "dataset_from_word2md": pipeline_info["dataset_source_path"],
        "dataset_with_local_llm": pipeline_info["dataset_path"],
        "local_llm_predictions": pipeline_info["prediction_path"],
        "comment_output_dir": str(comment_output_dir),
        "comment_doc_count": len(comment_summary.get("contracts", [])),
    }
    _write_json(output_root / "pipeline_summary.json", summary_payload)

    print(f"output root: {output_root}")
    print(f"dataset: {pipeline_info['dataset_path']}")
    print(f"local predictions: {pipeline_info['prediction_path']}")
    print(f"comment docs: {comment_output_dir}")


if __name__ == "__main__":
    main()
