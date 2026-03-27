from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .export_parallel_reports_to_xlsx import export_markdown_to_xlsx
from .io_utils import write_text
from .label_parser import classify_status, extract_status_reason
from .markdown_table_export import convert_markdown_file_to_html


LOCAL_LLM_AUTHOR = "local_llm"


@dataclass(frozen=True)
class ManualFeedbackItem:
    """One reviewed manual-feedback item derived from comment anchors."""

    contract_id: str
    paragraph_index: int
    clause_text: str
    model_comment: str
    reviewer_comment: str
    result: str
    status: str
    status_reason: str
    title: str
    explanation: str
    suggestion: str


@dataclass(frozen=True)
class ManualFeedbackContractAudit:
    """Manual-feedback audit for one contract."""

    contract_id: str
    source_md: Path
    meta_path: Path
    item_rows: list[ManualFeedbackItem]
    model_output_count: int
    reviewed_count: int
    tp: int
    fp: int
    fn: int
    unreviewed: int


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _safe_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _comment_id_key(value: Any) -> tuple[int, str]:
    text = str(value or "")
    if text.isdigit():
        return (0, f"{int(text):08d}")
    return (1, text)


def _parse_structured_comment(comment_text: str) -> tuple[str, str, str]:
    compact = _safe_text(comment_text)
    if not compact:
        return "", "", ""

    title_match = re.search(r"(?:风险点|问题|提示)[:：]\s*(.+?)(?=(?:说明|原因|建议|修改建议)[:：]|$)", compact)
    explanation_match = re.search(r"(?:说明|原因)[:：]\s*(.+?)(?=(?:建议|修改建议)[:：]|$)", compact)
    suggestion_match = re.search(r"(?:建议|修改建议)[:：]\s*(.+)$", compact)

    title = _safe_text(title_match.group(1)) if title_match else ""
    explanation = _safe_text(explanation_match.group(1)) if explanation_match else ""
    suggestion = _safe_text(suggestion_match.group(1)) if suggestion_match else ""

    if not title:
        title = compact[:30]
    return title, explanation, suggestion


def _review_result_from_status(status: str, *, has_model_comment: bool) -> str:
    if not has_model_comment:
        return "FN"
    if status in {"accept", "partial"}:
        return "TP"
    if status == "reject":
        return "FP"
    return "UNREVIEWED"


def _build_item(
    *,
    contract_id: str,
    paragraph_index: int,
    clause_text: str,
    model_comment: str,
    reviewer_comment: str,
) -> ManualFeedbackItem:
    status = classify_status(reviewer_comment)
    status_reason = extract_status_reason(reviewer_comment) if reviewer_comment else ""
    title, explanation, suggestion = _parse_structured_comment(model_comment or reviewer_comment)
    result = _review_result_from_status(status, has_model_comment=bool(model_comment))
    return ManualFeedbackItem(
        contract_id=contract_id,
        paragraph_index=paragraph_index,
        clause_text=_safe_text(clause_text),
        model_comment=_safe_text(model_comment),
        reviewer_comment=_safe_text(reviewer_comment),
        result=result,
        status=status,
        status_reason=status_reason,
        title=title,
        explanation=explanation,
        suggestion=suggestion,
    )


def build_contract_audit(contract_id: str, source_md: Path, meta_path: Path) -> ManualFeedbackContractAudit:
    """Build a manual-feedback audit from one `word2md` meta file."""

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    anchors = payload.get("comment_anchors") or []
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in anchors:
        if not isinstance(item, dict):
            continue
        paragraph_index = int(item.get("paragraph_index") or 0)
        if paragraph_index <= 0:
            continue
        grouped.setdefault(paragraph_index, []).append(item)

    item_rows: list[ManualFeedbackItem] = []
    model_output_count = 0
    for paragraph_index in sorted(grouped):
        paragraph_items = sorted(grouped[paragraph_index], key=lambda data: _comment_id_key(data.get("comment_id")))
        clause_text = _safe_text(paragraph_items[0].get("paragraph_excerpt", ""))
        local_items = [item for item in paragraph_items if _safe_text(item.get("author")) == LOCAL_LLM_AUTHOR]
        reviewer_items = [item for item in paragraph_items if _safe_text(item.get("author")) != LOCAL_LLM_AUTHOR]
        model_output_count += len(local_items)

        paired_count = min(len(local_items), len(reviewer_items))
        for index in range(paired_count):
            item_rows.append(
                _build_item(
                    contract_id=contract_id,
                    paragraph_index=paragraph_index,
                    clause_text=clause_text,
                    model_comment=_safe_text(local_items[index].get("comment_text", "")),
                    reviewer_comment=_safe_text(reviewer_items[index].get("comment_text", "")),
                )
            )

        for extra_local in local_items[paired_count:]:
            item_rows.append(
                _build_item(
                    contract_id=contract_id,
                    paragraph_index=paragraph_index,
                    clause_text=clause_text,
                    model_comment=_safe_text(extra_local.get("comment_text", "")),
                    reviewer_comment="",
                )
            )

        for extra_reviewer in reviewer_items[paired_count:]:
            item_rows.append(
                _build_item(
                    contract_id=contract_id,
                    paragraph_index=paragraph_index,
                    clause_text=clause_text,
                    model_comment="",
                    reviewer_comment=_safe_text(extra_reviewer.get("comment_text", "")),
                )
            )

    reviewed_count = sum(1 for item in item_rows if item.result in {"TP", "FP", "FN"})
    tp = sum(1 for item in item_rows if item.result == "TP")
    fp = sum(1 for item in item_rows if item.result == "FP")
    fn = sum(1 for item in item_rows if item.result == "FN")
    unreviewed = sum(1 for item in item_rows if item.result == "UNREVIEWED")
    return ManualFeedbackContractAudit(
        contract_id=contract_id,
        source_md=source_md,
        meta_path=meta_path,
        item_rows=item_rows,
        model_output_count=model_output_count,
        reviewed_count=reviewed_count,
        tp=tp,
        fp=fp,
        fn=fn,
        unreviewed=unreviewed,
    )


def load_manual_feedback_audits(run_root: Path) -> list[ManualFeedbackContractAudit]:
    """Load all manual-feedback audits from one `word2md` output batch."""

    audits: list[ManualFeedbackContractAudit] = []
    for meta_path in sorted(run_root.glob("*/meta.json")):
        source_md = meta_path.with_name("output.md")
        if not source_md.exists():
            continue
        audits.append(build_contract_audit(meta_path.parent.name, source_md, meta_path))
    return audits


def render_contract_report(audit: ManualFeedbackContractAudit) -> str:
    """Render one contract-level manual-feedback report."""

    lines = [
        f"# {audit.contract_id} 人工反馈评测",
        "",
        "## 指标概览",
        "",
        f"- 模型输出数: `{audit.model_output_count}`",
        f"- 已人工判定数: `{audit.reviewed_count}`",
        f"- TP: `{audit.tp}`",
        f"- FP: `{audit.fp}`",
        f"- FN: `{audit.fn}`",
        f"- 未判定: `{audit.unreviewed}`",
        f"- Markdown: `{audit.source_md}`",
        f"- Meta: `{audit.meta_path}`",
        "",
        "## 明细",
        "",
        "| 段落 | 结果 | 采纳状态 | 风险点 | 原文条款 | 模型批注 | 人工反馈 | 原因 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in audit.item_rows:
        lines.append(
            "| {paragraph} | {result} | {status} | {title} | {clause} | {model} | {review} | {reason} |".format(
                paragraph=item.paragraph_index,
                result=item.result,
                status=item.status or "other",
                title=item.title.replace("|", "\\|"),
                clause=item.clause_text.replace("|", "\\|"),
                model=item.model_comment.replace("|", "\\|"),
                review=item.reviewer_comment.replace("|", "\\|"),
                reason=item.status_reason.replace("|", "\\|"),
            )
        )
    return "\n".join(lines) + "\n"


def render_overall_summary(audits: list[ManualFeedbackContractAudit], run_label: str) -> str:
    """Render one overall summary report."""

    total_outputs = sum(audit.model_output_count for audit in audits)
    total_reviewed = sum(audit.reviewed_count for audit in audits)
    total_tp = sum(audit.tp for audit in audits)
    total_fp = sum(audit.fp for audit in audits)
    total_fn = sum(audit.fn for audit in audits)
    total_unreviewed = sum(audit.unreviewed for audit in audits)
    adoption_rate = _ratio(total_tp, total_reviewed)
    rejection_rate = _ratio(total_fp, total_reviewed)
    miss_rate = _ratio(total_fn, total_tp + total_fn)
    reviewed_coverage = _ratio(total_reviewed, total_outputs + total_fn)

    lines = [
        f"# {run_label} 人工反馈总体汇总",
        "",
        "## 总体指标",
        "",
        f"- 合同数: `{len(audits)}`",
        f"- 模型输出数: `{total_outputs}`",
        f"- 已人工判定数: `{total_reviewed}`",
        f"- TP: `{total_tp}`",
        f"- FP: `{total_fp}`",
        f"- FN: `{total_fn}`",
        f"- 未判定: `{total_unreviewed}`",
        "",
        "## 合同分项",
        "",
        "| 合同 | 模型输出数 | 已人工判定数 | TP | FP | FN | 未判定 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for audit in audits:
        lines.append(
            f"| {audit.contract_id.replace('|', '\\|')} | {audit.model_output_count} | {audit.reviewed_count} | {audit.tp} | {audit.fp} | {audit.fn} | {audit.unreviewed} |"
        )
    lines.extend(
        [
            "",
            "## 总结分析",
            "",
            f"- 当前这批人工反馈里，模型共输出 `{total_outputs}` 条风险点，其中被人工认可或部分认可 `{total_tp}` 条，明确未采纳 `{total_fp}` 条，另有人工补充且模型未报出的 `{total_fn}` 条。",
            f"- 从人工判定结果看，模型已经具备一定命中能力，但误报仍然偏多：采纳率 `{adoption_rate:.1%}`，未采纳率 `{rejection_rate:.1%}`。",
            f"- 漏报侧目前看到 `{total_fn}` 条，按 `FN / (TP + FN)` 粗算漏报率约 `{miss_rate:.1%}`，说明模型并非只存在误报，也仍有少量关键风险点没有覆盖到。",
            f"- 这批数据的人工反馈覆盖率约 `{reviewed_coverage:.1%}`。如果后续这个比例下降，就要警惕“未判定项”拉低结论可信度。",
            "- 当前配对逻辑主要依赖 `meta.json` 中的 `paragraph_index`、批注作者，以及同段内批注的先后顺序，因此更适合作为本轮复盘口径，而不是严格语义对齐标注。",
            "- 如果后面这类数据会持续积累，建议补一层更稳的批注配对标识或显式 ID，这样 TP / FP / FN 的统计会更稳定，也更适合长期横向比较。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_manual_feedback_reports(
    run_root: Path,
    output_dir: Path,
    *,
    run_label: str,
) -> dict[str, str | list[str]]:
    """Generate `md/html/xlsx` reports for one manual-feedback batch."""

    audits = load_manual_feedback_audits(run_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[str] = []
    for audit in audits:
        contract_dir = output_dir / audit.contract_id
        markdown_path = contract_dir / f"{audit.contract_id}_人工反馈评测.md"
        write_text(markdown_path, render_contract_report(audit))
        artifacts.append(str(markdown_path))

        html_path = markdown_path.with_suffix(".html")
        convert_markdown_file_to_html(markdown_path, html_path)
        artifacts.append(str(html_path))

        try:
            xlsx_path = markdown_path.with_suffix(".xlsx")
            export_markdown_to_xlsx(markdown_path, xlsx_path)
            artifacts.append(str(xlsx_path))
        except RuntimeError:
            pass

    summary_dir = output_dir / "总体汇总"
    summary_path = summary_dir / f"{run_label}_人工反馈总体汇总.md"
    write_text(summary_path, render_overall_summary(audits, run_label))
    artifacts.append(str(summary_path))

    summary_html = summary_path.with_suffix(".html")
    convert_markdown_file_to_html(summary_path, summary_html)
    artifacts.append(str(summary_html))

    try:
        summary_xlsx = summary_path.with_suffix(".xlsx")
        export_markdown_to_xlsx(summary_path, summary_xlsx)
        artifacts.append(str(summary_xlsx))
    except RuntimeError:
        pass

    return {
        "run_root": str(run_root),
        "output_dir": str(output_dir),
        "artifacts": artifacts,
    }
