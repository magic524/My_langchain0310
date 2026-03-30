from __future__ import annotations

import re
from pathlib import Path

from .io_utils import read_json, read_text
from .parse_utils import clean_markdown_cell, parse_markdown_table, split_markdown_tables, split_numbered_sections
from .text_utils import compact_text
from .review_types import RiskItem


def classify_status(text: str) -> str:
    """规范化采纳状态。"""

    normalized = compact_text(text)
    if not normalized:
        return "other"
    if "部分采纳" in normalized:
        return "partial"
    if "未采纳" in normalized or "不采纳" in normalized:
        return "reject"
    if "采纳" in normalized:
        return "accept"
    return "other"


def extract_status_reason(text: str) -> str:
    """提取采纳原因。"""

    matched = re.search(r"(?:原因|理由)[:：]\s*(.+)", text)
    if matched:
        return compact_text(matched.group(1))
    return compact_text(text)


def extract_inline_status(section_text: str) -> tuple[str, str]:
    """从正文内嵌的批注文本中兜底提取采纳状态。"""

    compact = compact_text(section_text)
    matched = re.search(r"批注.*?(部分采纳|未采纳|不采纳|采纳)(.*)", compact)
    if not matched:
        return "other", ""

    status_text = matched.group(1)
    tail_text = compact_text(matched.group(2))
    return classify_status(status_text), extract_status_reason(tail_text)


def _index_from_excerpt(excerpt: str) -> int | None:
    matched = re.match(r"\s*(\d+)\s*[、.．]", excerpt)
    if not matched:
        return None
    return int(matched.group(1))


def parse_status_map(meta_path: Path) -> dict[int, str]:
    """从 meta.json 的批注里构建状态表。"""

    payload = read_json(meta_path)
    anchors = payload.get("comment_anchors") or []
    by_index: dict[int, list[str]] = {}
    for item in anchors:
        if not isinstance(item, dict):
            continue
        excerpt = str(item.get("paragraph_excerpt", ""))
        index = _index_from_excerpt(excerpt)
        if index is None:
            continue
        comment_text = compact_text(str(item.get("comment_text", "")))
        if not comment_text:
            continue
        by_index.setdefault(index, []).append(comment_text)
    return {index: " | ".join(items) for index, items in by_index.items()}


def _parse_table_fields(lines: list[str]) -> tuple[str, str, str]:
    """从标签表格中抽取条款原文、修改理由和修改建议。"""

    tables = split_markdown_tables(lines)
    if not tables:
        return "", "", ""

    rows = parse_markdown_table(tables[0])
    if not rows:
        return "", "", ""

    clean_rows = [[clean_markdown_cell(cell) for cell in row] for row in rows]
    clause_text = ""
    suggestion = ""
    explanation = ""

    if len(clean_rows) >= 2 and clean_rows[0]:
        header = "".join(clean_rows[0])
        if "条款原文" in header:
            row = clean_rows[1]
            clause_text = row[0] if len(row) >= 1 else ""
            suggestion = row[1] if len(row) >= 2 else ""

    for index, row in enumerate(clean_rows):
        first_cell = row[0] if row else ""
        if "修改理由" in first_cell and index + 1 < len(clean_rows):
            next_row = [cell for cell in clean_rows[index + 1] if cell]
            explanation = max(next_row, key=len) if next_row else ""
            break

    return compact_text(clause_text), compact_text(explanation), compact_text(suggestion)


def parse_label_markdown(contract_id: str, adoption_md_path: Path, adoption_meta_path: Path) -> list[RiskItem]:
    """解析采纳情况说明。"""

    markdown_text = read_text(adoption_md_path)
    status_map = parse_status_map(adoption_meta_path)
    risks: list[RiskItem] = []

    for block in split_numbered_sections(markdown_text):
        section_text = "\n".join(block.lines)
        clause_text, explanation, suggestion = _parse_table_fields(block.lines)
        status_text = status_map.get(block.index, "")
        status = classify_status(status_text)
        status_reason = extract_status_reason(status_text) if status_text else ""
        if status == "other":
            inline_status, inline_reason = extract_inline_status(section_text)
            status = inline_status
            if inline_reason:
                status_reason = inline_reason
        if not explanation:
            matched = re.search(r"(?:修改理由|风险说明|问题说明)[:：]\s*(.+)", section_text)
            explanation = compact_text(matched.group(1)) if matched else ""
        if not suggestion:
            matched = re.search(r"(?:修改建议|建议修改)[:：]\s*(.+)", section_text)
            suggestion = compact_text(matched.group(1)) if matched else ""

        risks.append(
            RiskItem(
                risk_id=f"{contract_id}_label_{block.index:03d}",
                contract_id=contract_id,
                title=block.title,
                clause_text=clause_text,
                explanation=explanation,
                suggestion=suggestion,
                source_excerpt=compact_text(" ".join(block.lines[:8])),
                status=status,
                status_reason=status_reason,
            )
        )
    return risks

