from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
METRICS_V2_ROOT = CURRENT_FILE.parents[1]
SRC_ROOT = METRICS_V2_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from contract_metrics_v2.evaluator import evaluate_dataset  # noqa: E402
from contract_metrics_v2.markdown_table_export import convert_markdown_file_to_html  # noqa: E402
from contract_metrics_v2.parallel_review_report import (  # noqa: E402
    load_parallel_audits,
    write_contract_parallel_report,
    write_overall_summary_report,
)
from contract_metrics_v2.reporter import write_reports  # noqa: E402
from export_parallel_reports_to_xlsx import export_markdown_to_xlsx  # noqa: E402
from format_parallel_reports_for_client import process_markdown_dir  # noqa: E402


RISK_MARKER = "【风险点】"
EXPLANATION_MARKER = "【说明】"
SUGGESTION_MARKER = "【修改建议】"


def _extract_between(text: str, start: str, end_markers: tuple[str, ...]) -> str:
    if start not in text:
        return ""
    segment = text.split(start, 1)[1]
    end_positions = [segment.find(marker) for marker in end_markers if marker in segment]
    if end_positions:
        segment = segment[: min(end_positions)]
    return re.sub(r"\s+", " ", segment).strip(" ；，。】")


def _safe_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


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
        # 跳过完全空洞的抽取结果。
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


def _merge_third_party_risks(
    old_risks: list[dict[str, Any]],
    new_risks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Select third-party risks with a conservative, stable strategy.

    Strategy:
    - Prefer `new_risks` when parser can recover results from the source markdown.
    - Fallback to `old_risks` only when `new_risks` is empty.

    This avoids inflating prediction counts from union-merging two heterogeneous
    sources that may contain near-duplicate or semantically overlapping items.
    """
    if new_risks:
        return new_risks, "prefer_parsed_only"
    if old_risks:
        return old_risks, "fallback_old_only"
    return [], "merged(empty)"


def _collect_contract_metric(
    payload: dict[str, Any],
    *,
    contract_id: str,
    participant: str,
    policy: str,
) -> dict[str, int] | None:
    for row in payload.get("contract_results", []):
        if not isinstance(row, dict):
            continue
        if row.get("contract_id") != contract_id:
            continue
        if row.get("participant") != participant or row.get("policy") != policy:
            continue
        risk = row.get("risk_metrics") or {}
        clause = row.get("clause_metrics") or {}
        return {
            "risk_tp": int(risk.get("tp", 0)),
            "risk_fp": int(risk.get("fp", 0)),
            "risk_fn": int(risk.get("fn", 0)),
            "clause_tp": int(clause.get("tp", 0)),
            "clause_fp": int(clause.get("fp", 0)),
            "clause_fn": int(clause.get("fn", 0)),
        }
    return None


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


def _merge_local_llm_predictions(
    dataset_payload: dict[str, Any],
    *,
    run_outputs_dir: Path,
    run_id: str,
) -> None:
    local_by_contract: dict[str, list[dict[str, Any]]] = {}
    if run_outputs_dir.exists():
        for child in run_outputs_dir.iterdir():
            if not child.is_dir() or not child.name.startswith(run_id):
                continue
            dataset_path = child / "dataset_with_local_llm.json"
            if not dataset_path.exists():
                continue
            payload = _load_json(dataset_path)
            for contract in payload.get("contracts", []):
                if not isinstance(contract, dict):
                    continue
                contract_id = str(contract.get("contract_id", ""))
                participants = contract.get("participants") or {}
                local_risks = participants.get("local_llm") if isinstance(participants, dict) else None
                if contract_id and isinstance(local_risks, list):
                    local_by_contract[contract_id] = local_risks

    for contract in dataset_payload.get("contracts", []):
        if not isinstance(contract, dict):
            continue
        contract_id = str(contract.get("contract_id", ""))
        if contract_id in local_by_contract:
            contract.setdefault("participants", {})["local_llm"] = local_by_contract[contract_id]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run isolated third_party parsing fix experiment")
    parser.add_argument("--run-id", default="20260317_word2md_eval", help="word2md run id")
    parser.add_argument(
        "--source-run-dir",
        default="",
        help="Existing local_llm output directory containing dataset_with_local_llm.json",
    )
    parser.add_argument(
        "--output-root",
        default="",
        help="Isolated output root. Default: metrics_v2/local_llm/outputs_fix/<run_id>_third_party_fix_<date>",
    )
    args = parser.parse_args()

    source_run_dir = (
        Path(args.source_run_dir).resolve()
        if args.source_run_dir
        else (METRICS_V2_ROOT / "local_llm" / "outputs" / args.run_id).resolve()
    )
    source_dataset_path = source_run_dir / "dataset_with_local_llm.json"
    if not source_dataset_path.exists():
        # 当前仓库通常按合同拆分 local_llm 输出，这里回落到总数据集并自动合并 local_llm 预测。
        source_dataset_path = (
            METRICS_V2_ROOT / "outputs" / "datasets" / f"dataset_{args.run_id}.json"
        ).resolve()
    if not source_dataset_path.exists():
        msg = f"source dataset 不存在: {source_dataset_path}"
        raise FileNotFoundError(msg)

    date_tag = datetime.now().strftime("%Y%m%d")
    output_root = (
        Path(args.output_root).resolve()
        if args.output_root
        else (METRICS_V2_ROOT / "local_llm" / "outputs_fix" / f"{args.run_id}_third_party_fix_{date_tag}").resolve()
    )
    output_root.mkdir(parents=True, exist_ok=True)

    dataset_payload = _load_json(source_dataset_path)
    _merge_local_llm_predictions(
        dataset_payload,
        run_outputs_dir=(METRICS_V2_ROOT / "local_llm" / "outputs").resolve(),
        run_id=args.run_id,
    )

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

    fixed_dataset_path = output_root / "dataset_with_local_llm.json"
    _write_json(fixed_dataset_path, dataset_payload)
    _write_json(output_root / "third_party_fix_change_log.json", {"changes": change_log})

    participants = _participants_from_dataset(dataset_payload)
    evaluation_payload = evaluate_dataset(fixed_dataset_path, participants=participants)
    report_files = write_reports(output_root, evaluation_payload)

    per_contract_run_dirs = _write_single_contract_run_dirs(
        dataset_payload,
        output_root=output_root,
        participants=participants,
    )

    compare_dir = output_root / "细节对比_fix"
    markdown_files = _write_parallel_reports(per_contract_run_dirs, compare_dir, prefix=args.run_id)
    markdown_files = process_markdown_dir(compare_dir)
    _export_html(markdown_files)
    _export_xlsx(markdown_files)

    summary = {
        "source_run_dir": str(source_run_dir),
        "output_root": str(output_root),
        "fixed_dataset": str(fixed_dataset_path),
        "evaluation_report": report_files["markdown"],
        "evaluation_json": report_files["json"],
        "compare_markdown_count": len(markdown_files),
        "compare_dir": str(compare_dir),
    }
    _write_json(output_root / "fix_experiment_summary.json", summary)

    before_eval = evaluate_dataset(source_dataset_path, participants=participants)
    before_path = output_root / "evaluation_report_before_fix.json"
    _write_json(before_path, {
        "meta": before_eval.meta,
        "warnings": before_eval.warnings,
        "participant_results": [
            {
                "participant": row.participant,
                "policy": row.policy,
                "clause_metrics": {
                    "tp": row.clause_metrics.tp,
                    "fp": row.clause_metrics.fp,
                    "fn": row.clause_metrics.fn,
                },
                "risk_metrics": {
                    "tp": row.risk_metrics.tp,
                    "fp": row.risk_metrics.fp,
                    "fn": row.risk_metrics.fn,
                },
            }
            for row in before_eval.participant_results
        ],
        "contract_results": before_eval.contract_results,
    })

    target_contract = "3-保密协议"
    target_participant = "third_party"
    target_policy = "adopted_only"
    before_metrics = _collect_contract_metric(
        {
            "contract_results": before_eval.contract_results,
        },
        contract_id=target_contract,
        participant=target_participant,
        policy=target_policy,
    )
    after_metrics = _collect_contract_metric(
        {
            "contract_results": evaluation_payload.contract_results,
        },
        contract_id=target_contract,
        participant=target_participant,
        policy=target_policy,
    )

    print(f"source run dir: {source_run_dir}")
    print(f"fixed output dir: {output_root}")
    print(f"fixed dataset: {fixed_dataset_path}")
    print(f"evaluation report: {report_files['markdown']}")
    print(f"comparison markdown dir: {compare_dir}")
    print(f"target before ({target_contract}/{target_participant}/{target_policy}): {before_metrics}")
    print(f"target after  ({target_contract}/{target_participant}/{target_policy}): {after_metrics}")


if __name__ == "__main__":
    main()
