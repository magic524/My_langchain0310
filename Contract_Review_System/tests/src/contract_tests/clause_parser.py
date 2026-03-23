from __future__ import annotations

from .parse_utils import is_bold_section_line, is_clause_start, is_heading_line
from .text_utils import compact_text, short_preview
from .types import ClauseUnit


def _clean_line(line: str) -> str:
    """清洗原始 markdown 行。"""

    stripped = line.strip()
    if not stripped or stripped == "<!-- image -->":
        return ""
    return compact_text(stripped)


def extract_clause_units(contract_id: str, markdown_text: str) -> list[ClauseUnit]:
    """把原合同 markdown 拆成条款块，并补齐最小上下文。"""

    lines = [_clean_line(line) for line in markdown_text.splitlines()]
    lines = [line for line in lines if line]

    raw_blocks: list[dict[str, str]] = []
    section_title = ""
    current_title = ""
    current_lines: list[str] = []
    block_index = 0

    def flush_current() -> None:
        nonlocal current_title, current_lines, block_index
        if not current_lines:
            return
        block_index += 1
        clause_title = current_title or short_preview(" ".join(current_lines), limit=24)
        raw_blocks.append(
            {
                "clause_id": f"{contract_id}_c{block_index:03d}",
                "section_title": section_title,
                "clause_title": clause_title,
                "clause_text": compact_text("\n".join(current_lines)),
            }
        )
        current_title = ""
        current_lines = []

    for line in lines:
        if is_heading_line(line):
            continue

        if is_bold_section_line(line):
            flush_current()
            section_title = line.strip("*")
            continue

        if is_clause_start(line):
            flush_current()
            current_title = line
            current_lines = [line]
            continue

        if not current_lines:
            current_title = section_title or short_preview(line, limit=24)
            current_lines = [line]
            continue
        current_lines.append(line)

    flush_current()

    clauses: list[ClauseUnit] = []
    for index, block in enumerate(raw_blocks):
        prev_preview = raw_blocks[index - 1]["clause_title"] if index > 0 else ""
        next_preview = raw_blocks[index + 1]["clause_title"] if index + 1 < len(raw_blocks) else ""
        context_text = "\n".join(
            [
                f"章节标题：{block['section_title'] or '未识别'}",
                f"上一条款摘要：{prev_preview or '无'}",
                f"当前条款：{block['clause_text']}",
                f"下一条款摘要：{next_preview or '无'}",
            ]
        )
        clauses.append(
            ClauseUnit(
                clause_id=block["clause_id"],
                contract_id=contract_id,
                section_title=block["section_title"],
                clause_title=block["clause_title"],
                clause_text=block["clause_text"],
                prev_clause_preview=prev_preview,
                next_clause_preview=next_preview,
                context_text=context_text,
            )
        )
    return clauses
