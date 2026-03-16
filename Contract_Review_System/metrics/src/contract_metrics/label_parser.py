from __future__ import annotations

import re
from pathlib import Path

from .io_utils import read_json, read_text
from .parse_utils import (
    clean_markdown_cell,
    extract_inline_comment,
    parse_markdown_table,
    split_markdown_tables,
    split_numbered_sections,
)
from .text_utils import compact_text
from .types import RiskEntry


def classify_label_status(text: str) -> str:
    """Normalize label status text.

    Args:
        text: Raw comment text.

    Returns:
        One of `accept`, `partial`, `reject`, `other`.
    """
    normalized = text.strip()
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
    """Extract reason text from comments.

    Args:
        text: Raw status comment.

    Returns:
        Reason text.
    """
    patterns = (r"原因[:：]\s*(.+)", r"理由[:：]\s*(.+)")
    for pattern in patterns:
        matched = re.search(pattern, text)
        if matched:
            return compact_text(matched.group(1))
    return compact_text(text)


def _index_from_paragraph_excerpt(excerpt: str) -> int | None:
    matched = re.match(r"\s*(\d+)\s*[、\.．]", excerpt)
    if not matched:
        return None
    return int(matched.group(1))


def parse_label_meta_status(meta_path: Path) -> dict[int, str]:
    """Build heading-index to status comment map from label meta.

    Args:
        meta_path: `meta.json` path for adoption markdown.

    Returns:
        Mapping from numeric heading index to concatenated comment text.
    """
    payload = read_json(meta_path)
    comments = payload.get("comment_anchors") or []
    if not isinstance(comments, list):
        return {}

    by_index: dict[int, list[str]] = {}
    for item in comments:
        if not isinstance(item, dict):
            continue
        excerpt = str(item.get("paragraph_excerpt", "")).strip()
        idx = _index_from_paragraph_excerpt(excerpt)
        if idx is None:
            continue

        text = compact_text(str(item.get("comment_text", "")))
        if not text:
            continue
        by_index.setdefault(idx, []).append(text)

    return {idx: " | ".join(values) for idx, values in by_index.items()}


def _parse_table_fields(section_lines: list[str]) -> tuple[str, str, str]:
    """Parse clause/explanation/suggestion fields from table block.

    Args:
        section_lines: Section lines.

    Returns:
        Tuple of `(clause_text, explanation, suggestion)`.
    """
    clause_text = ""
    explanation = ""
    suggestion = ""

    tables = split_markdown_tables(section_lines)
    if not tables:
        return clause_text, explanation, suggestion

    rows = parse_markdown_table(tables[0])
    if not rows:
        return clause_text, explanation, suggestion

    cleaned_rows = [[clean_markdown_cell(cell) for cell in row] for row in rows]

    if len(cleaned_rows) >= 2 and "条款原文" in cleaned_rows[0][0]:
        first_data = cleaned_rows[1]
        clause_text = first_data[0] if len(first_data) >= 1 else ""
        suggestion = first_data[1] if len(first_data) >= 2 else ""

    for row_index, row in enumerate(cleaned_rows):
        if not row:
            continue
        if "修改理由" in row[0] and row_index + 1 < len(cleaned_rows):
            next_row = cleaned_rows[row_index + 1]
            candidates = [value for value in next_row if value]
            explanation = max(candidates, key=len) if candidates else explanation
            break

    return clause_text, explanation, suggestion


def _fallback_explanation(section_text: str) -> str:
    patterns = (
        r"风险说明[:：]\s*(.+)",
        r"问题说明[:：]\s*(.+)",
        r"修改理由[:：]\s*(.+)",
    )
    for pattern in patterns:
        matched = re.search(pattern, section_text)
        if matched:
            return compact_text(matched.group(1))
    return ""


def _fallback_suggestion(section_text: str) -> str:
    matched = re.search(r"修改建议[:：]\s*(.+)", section_text)
    if not matched:
        return ""
    return compact_text(matched.group(1))


def parse_label_markdown(
    *,
    contract_id: str,
    adoption_md_path: Path,
    adoption_meta_path: Path,
) -> list[RiskEntry]:
    """Parse adoption markdown into label risk entries.

    Args:
        contract_id: Contract identifier.
        adoption_md_path: Adoption `output.md` path.
        adoption_meta_path: Adoption `meta.json` path.

    Returns:
        Parsed label entries.
    """
    markdown_text = read_text(adoption_md_path)
    sections = split_numbered_sections(markdown_text)
    status_map = parse_label_meta_status(adoption_meta_path)

    risks: list[RiskEntry] = []
    for block in sections:
        heading_line = block.lines[0] if block.lines else ""
        inline_comment = extract_inline_comment(heading_line)
        meta_comment = status_map.get(block.index, "")

        status_text = inline_comment or meta_comment
        status = classify_label_status(status_text)
        status_reason = extract_status_reason(status_text) if status_text else ""

        section_text = "\n".join(block.lines)
        clause_text, explanation, suggestion = _parse_table_fields(block.lines)

        if not explanation:
            explanation = _fallback_explanation(section_text)
        if not suggestion:
            suggestion = _fallback_suggestion(section_text)

        source_excerpt = compact_text(" ".join(block.lines[:8]))
        risks.append(
            RiskEntry(
                risk_id=f"{contract_id}_label_{block.index:03d}",
                contract_id=contract_id,
                title=block.title,
                clause_text=clause_text,
                explanation=explanation,
                suggestion=suggestion,
                source_excerpt=source_excerpt,
                status=status,
                status_reason=status_reason,
            )
        )

    return risks
