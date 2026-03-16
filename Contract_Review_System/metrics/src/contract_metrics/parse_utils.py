from __future__ import annotations

import re
from dataclasses import dataclass


HEADING_RE = re.compile(
    r"^\s*(?:\*{1,2})?(?P<index>\d+)\s*[、\.．]\s*(?P<title>.+?)(?:\*{1,2})?\s*(?:【批注#.*)?$"
)


@dataclass(slots=True)
class SectionBlock:
    """Numbered markdown section block."""

    index: int
    title: str
    start_line: int
    lines: list[str]


def split_numbered_sections(markdown_text: str) -> list[SectionBlock]:
    """Split markdown text by numbered headings.

    Args:
        markdown_text: Input markdown text.

    Returns:
        Numbered section list.
    """
    lines = markdown_text.splitlines()
    sections: list[SectionBlock] = []
    current: SectionBlock | None = None

    for line_no, line in enumerate(lines, start=1):
        matched = HEADING_RE.match(line.strip())
        if matched:
            if current is not None:
                sections.append(current)
            current = SectionBlock(
                index=int(matched.group("index")),
                title=matched.group("title").strip(),
                start_line=line_no,
                lines=[line],
            )
            continue

        if current is not None:
            current.lines.append(line)

    if current is not None:
        sections.append(current)
    return sections


def split_markdown_tables(lines: list[str]) -> list[list[str]]:
    """Find contiguous markdown table blocks.

    Args:
        lines: Line list.

    Returns:
        Table blocks, each containing raw table lines.
    """
    tables: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current.append(stripped)
            continue

        if current:
            tables.append(current)
            current = []

    if current:
        tables.append(current)

    return tables


def parse_markdown_table(table_lines: list[str]) -> list[list[str]]:
    """Parse a markdown table into row cells.

    Args:
        table_lines: Table line block.

    Returns:
        Parsed rows.
    """
    rows: list[list[str]] = []
    for raw in table_lines:
        cells = [cell.strip() for cell in raw.strip("|").split("|")]
        if not cells:
            continue

        # Skip separator rows.
        if all(re.fullmatch(r"[:\-\s]+", cell or "") for cell in cells):
            continue
        rows.append(cells)

    return rows


def clean_markdown_cell(cell: str) -> str:
    """Strip lightweight markdown marks from table cells.

    Args:
        cell: Raw cell value.

    Returns:
        Cleaned value.
    """
    cleaned = re.sub(r"\*{1,2}", "", cell)
    cleaned = re.sub(r"~~", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_inline_comment(line: str) -> str:
    """Extract inline comment text in `【批注#...: ...】` format.

    Args:
        line: Input line.

    Returns:
        Comment content or empty string.
    """
    matched = re.search(r"【批注#\d+/[^:]+:\s*(.*?)】", line)
    if not matched:
        return ""
    return matched.group(1).strip()
