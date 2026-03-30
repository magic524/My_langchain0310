from __future__ import annotations

import re
from pathlib import Path

from .io_utils import read_text
from .parse_utils import clean_markdown_cell, parse_markdown_table, split_markdown_tables, split_numbered_sections
from .text_utils import compact_text
from .review_types import RiskItem


RISK_HINTS = (
    "风险",
    "问题",
    "瑕疵",
    "违约",
    "争议",
    "不明确",
    "缺失",
    "修改建议",
    "修改理由",
    "风险说明",
    "问题说明",
    "审查意见",
    "批注#",
)


def _signal_score(path: Path) -> int:
    """粗略衡量文件中的风险信号强度。"""

    try:
        text = read_text(path)
    except Exception:  # noqa: BLE001
        return 0
    return sum(text.count(marker) for marker in RISK_HINTS)


def _third_party_priority(path: Path) -> tuple[int, int, int]:
    """第三方文件优先级。

    v2 优先选择“批注版/修订批注版”，因为它们通常比总览型审查意见书更细粒度，
    更适合和采纳情况说明逐项对比。
    """

    text = str(path)
    name = path.parent.name
    if "修订批注版" in text or "修订批注版" in name:
        return (0, -_signal_score(path), len(text))
    if "批注版" in text or "批注版" in name:
        return (1, -_signal_score(path), len(text))
    if "修订版" in text or "修订版" in name:
        return (2, -_signal_score(path), len(text))
    if "详细审查意见" in text or "附件" in text:
        return (3, -_signal_score(path), len(text))
    if "审查意见书" in text:
        return (4, -_signal_score(path), len(text))
    return (5, -_signal_score(path), len(text))


def _estimated_risk_count(participant: str, path: Path) -> int:
    """估算某个候选文件能解析出的风险点数量。"""

    markdown_text = read_text(path)
    # 这里直接复用本模块的解析函数做轻量预判，数据量很小时比纯文件名猜测更稳。
    return len(_deduplicate(
        _parse_structured_report("preview", participant, markdown_text)
        + _parse_numbered_sections("preview", participant, markdown_text)
        + _parse_inline_comments("preview", participant, markdown_text)
    ))


def select_participant_markdown(contract_dir: Path, participant: str) -> Path | None:
    """为参与方挑选最合适的 markdown 文件。"""

    if participant == "third_party":
        root = contract_dir / "2-第三方平台审查结果"
        if not root.exists():
            return None
        candidates = sorted(root.rglob("output.md"))
    elif participant == "final_applied":
        candidates = sorted(path for path in contract_dir.rglob("output.md") if "3-" in path.parent.name)
    else:
        msg = f"不支持的 participant: {participant}"
        raise ValueError(msg)

    if not candidates:
        return None
    if participant == "third_party":
        return sorted(
            candidates,
            key=lambda path: (-_estimated_risk_count(participant, path), *_third_party_priority(path)),
        )[0]
    return sorted(candidates, key=lambda path: (-_signal_score(path), len(str(path))))[0]


def _contains_risk_signal(text: str) -> bool:
    """判断文本是否像一个风险点。"""

    return any(marker in text for marker in RISK_HINTS)


def _parse_table_fields(lines: list[str]) -> tuple[str, str, str]:
    """从表格中抽取条款、说明、建议。"""

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


def _parse_numbered_sections(contract_id: str, participant: str, markdown_text: str) -> list[RiskItem]:
    """解析编号型风险点。"""

    items: list[RiskItem] = []
    for block in split_numbered_sections(markdown_text):
        section_text = "\n".join(block.lines)
        clause_text, explanation, suggestion = _parse_table_fields(block.lines)
        if not explanation:
            matched = re.search(r"(?:风险说明|问题说明|修改理由)[:：]\s*(.+)", section_text)
            explanation = compact_text(matched.group(1)) if matched else ""
        if not suggestion:
            matched = re.search(r"(?:修改建议|建议修改)[:：]\s*(.+)", section_text)
            suggestion = compact_text(matched.group(1)) if matched else ""
        combined = " ".join([block.title, explanation, suggestion, clause_text, section_text[:120]])
        if not _contains_risk_signal(combined):
            continue
        items.append(
            RiskItem(
                risk_id=f"{contract_id}_{participant}_sec_{block.index:03d}",
                contract_id=contract_id,
                title=block.title,
                clause_text=clause_text,
                explanation=explanation,
                suggestion=suggestion,
                source_excerpt=compact_text(" ".join(block.lines[:8])),
            )
        )
    return items


def _parse_structured_report(contract_id: str, participant: str, markdown_text: str) -> list[RiskItem]:
    """解析“审查意见书”中的结构化风险提示。"""

    items: list[RiskItem] = []
    pattern = re.compile(
        r"\*\*(?P<index>\d+)\.\s*(?P<title>[^*]+?)\*\*(?P<body>.*?)(?=\n\*\*\d+\.\s*|\Z)",
        flags=re.DOTALL,
    )

    for matched in pattern.finditer(markdown_text):
        body = matched.group("body")
        clause_match = re.search(r"具体条款[:：]\s*(.+?)(?=\n\n(?:风险说明|修改建议|$))", body, flags=re.DOTALL)
        explanation_match = re.search(r"风险说明[:：]\s*(.+?)(?=\n\n(?:修改建议|$))", body, flags=re.DOTALL)
        suggestion_match = re.search(r"修改建议[:：]\s*(.+?)(?=\n\n|$)", body, flags=re.DOTALL)

        title = compact_text(matched.group("title"))
        clause_text = compact_text(clause_match.group(1)) if clause_match else ""
        explanation = compact_text(explanation_match.group(1)) if explanation_match else ""
        suggestion = compact_text(suggestion_match.group(1)) if suggestion_match else ""

        combined = " ".join([title, clause_text, explanation, suggestion])
        if not _contains_risk_signal(combined):
            continue
        items.append(
            RiskItem(
                risk_id=f"{contract_id}_{participant}_rep_{int(matched.group('index')):03d}",
                contract_id=contract_id,
                title=title,
                clause_text=clause_text,
                explanation=explanation,
                suggestion=suggestion,
                source_excerpt=compact_text(body[:240]),
            )
        )
    return items


def _parse_inline_comments(contract_id: str, participant: str, markdown_text: str) -> list[RiskItem]:
    """解析行内批注型风险点。"""

    items: list[RiskItem] = []
    index = 0
    comment_pattern = re.compile(r"【批注#\d+/[^:]+:\s*(.*?)】")
    structured_pattern = re.compile(
        r"【风险点】(?P<title>.*?)【说明】(?P<explanation>.*?)(?:【修改建议】(?P<suggestion>.*))?$"
    )

    for line in markdown_text.splitlines():
        for matched in comment_pattern.finditer(line):
            index += 1
            comment_text = compact_text(matched.group(1))
            if not _contains_risk_signal(comment_text):
                continue
            structured = structured_pattern.search(comment_text)
            title = comment_text[:28]
            explanation = comment_text
            suggestion = ""
            if structured:
                title = compact_text(structured.group("title"))
                explanation = compact_text(structured.group("explanation"))
                suggestion = compact_text(structured.group("suggestion") or "")
            clause_text = compact_text(comment_pattern.sub("", line))
            items.append(
                RiskItem(
                    risk_id=f"{contract_id}_{participant}_cmt_{index:03d}",
                    contract_id=contract_id,
                    title=title,
                    clause_text=clause_text,
                    explanation=explanation,
                    suggestion=suggestion,
                    source_excerpt=comment_text,
                )
            )
    return items


def _deduplicate(items: list[RiskItem]) -> list[RiskItem]:
    """对重复风险点去重。"""

    deduped: list[RiskItem] = []
    seen: set[str] = set()
    for item in items:
        key = "|".join(
            [
                item.title[:50],
                item.clause_text[:60],
                item.explanation[:60],
                item.suggestion[:60],
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def parse_participant_markdown(contract_id: str, participant: str, markdown_path: Path) -> list[RiskItem]:
    """解析参与方 markdown。"""

    markdown_text = read_text(markdown_path)
    items: list[RiskItem] = []
    items.extend(_parse_structured_report(contract_id, participant, markdown_text))
    items.extend(_parse_numbered_sections(contract_id, participant, markdown_text))
    items.extend(_parse_inline_comments(contract_id, participant, markdown_text))
    return _deduplicate(items)

