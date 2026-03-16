from __future__ import annotations

import re

from .text_utils import compact_text
from .types import ClauseRecord


def _is_low_value_line(line: str) -> bool:
    if not line.strip():
        return True
    if line.strip().startswith("|") and line.strip().endswith("|"):
        return True
    if line.strip().startswith("<!--"):
        return True
    if "【样式/" in line or "【批注#" in line:
        return True
    if line.strip().startswith("#"):
        return True
    return False


def _looks_like_clause(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 12:
        return False

    markers = (
        r"^\d+\s*[\.、]",
        r"^[一二三四五六七八九十]+[、]",
        r"^\*\*[一二三四五六七八九十]+、",
        r"^\*\*（[一二三四五六七八九十]+）",
    )
    if any(re.match(pattern, stripped) for pattern in markers):
        return True

    if re.search(r"[\u4e00-\u9fff]", stripped) and len(stripped) >= 24:
        return True

    return False


def extract_clause_units(contract_id: str, markdown_text: str) -> list[ClauseRecord]:
    """Extract clause units from original contract markdown.

    Args:
        contract_id: Contract identifier.
        markdown_text: Original contract markdown.

    Returns:
        Ordered clause records.
    """
    clauses: list[str] = []
    seen: set[str] = set()

    for raw_line in markdown_text.splitlines():
        if _is_low_value_line(raw_line):
            continue
        line = compact_text(raw_line)
        if not _looks_like_clause(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        clauses.append(line)

    return [
        ClauseRecord(
            clause_id=f"{contract_id}_c{index:03d}",
            clause_text=text,
        )
        for index, text in enumerate(clauses, start=1)
    ]
