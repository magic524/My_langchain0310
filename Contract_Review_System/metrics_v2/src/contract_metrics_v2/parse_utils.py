from __future__ import annotations

import re
from dataclasses import dataclass

from .text_utils import compact_text


@dataclass(slots=True)
class NumberedBlock:
    """编号段落块。"""

    index: int
    title: str
    lines: list[str]


def clean_markdown_cell(text: str) -> str:
    """清洗 markdown 表格单元格。"""

    cleaned = text.strip().strip("|").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def split_markdown_tables(lines: list[str]) -> list[list[str]]:
    """从文本块中拆出表格。"""

    tables: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if "|" in line:
            current.append(line)
            continue
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def parse_markdown_table(lines: list[str]) -> list[list[str]]:
    """把 markdown 表格解析成二维数组。"""

    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"\|?[\-\s:|]+\|?", stripped):
            continue
        parts = [clean_markdown_cell(cell) for cell in stripped.strip("|").split("|")]
        if any(parts):
            rows.append(parts)
    return rows


def is_heading_line(line: str) -> bool:
    """判断是否是标题行。"""

    return line.strip().startswith("#")


def is_bold_section_line(line: str) -> bool:
    """判断是否是粗体章节行。"""

    stripped = line.strip()
    return stripped.startswith("**") and stripped.endswith("**")


def is_clause_start(line: str) -> bool:
    """判断是否是条款起始行。"""

    stripped = line.strip()
    patterns = (
        r"^\d+[、.]",
        r"^\d+\.\d+",
        r"^[（(][一二三四五六七八九十0-9]+[）)]",
    )
    return any(re.match(pattern, stripped) for pattern in patterns)


def split_numbered_sections(markdown_text: str) -> list[NumberedBlock]:
    """把按编号组织的审查意见拆成段。"""

    lines = markdown_text.splitlines()
    blocks: list[NumberedBlock] = []
    current_lines: list[str] = []
    current_index: int | None = None
    current_title = ""

    for line in lines:
        stripped = line.strip()
        normalized = stripped
        if normalized.startswith("**") and normalized.endswith("**") and len(normalized) >= 4:
            normalized = normalized[2:-2].strip()
        matched = re.match(r"^(\d+)[、.]\s*(.+)$", normalized)
        if matched:
            if current_index is not None and current_lines:
                blocks.append(NumberedBlock(index=current_index, title=current_title, lines=current_lines))
            current_index = int(matched.group(1))
            current_title = compact_text(matched.group(2))
            current_lines = [line]
            continue

        if current_index is not None:
            current_lines.append(line)

    if current_index is not None and current_lines:
        blocks.append(NumberedBlock(index=current_index, title=current_title, lines=current_lines))
    return blocks
