from __future__ import annotations

import re
from pathlib import Path

from .io_utils import read_text
from .parse_utils import (
    clean_markdown_cell,
    parse_markdown_table,
    split_markdown_tables,
    split_numbered_sections,
)
from .text_utils import compact_text
from .types import RiskEntry


RISK_HINT_MARKERS = (
    "风险",
    "问题",
    "瑕疵",
    "违约",
    "争议",
    "不明确",
    "缺失",
    "缺乏",
    "不完整",
    "修改建议",
    "建议修改",
    "风险说明",
    "问题说明",
    "修改理由",
    "审查意见",
    "审查批注",
    "批注#",
)

STYLE_NOISE_MARKERS = (
    "样式/段落",
    "样式/",
    "color#",
    "underline",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _is_style_only_comment(text: str) -> bool:
    if not text:
        return False
    if _contains_any(text, RISK_HINT_MARKERS):
        return False
    return _contains_any(text, STYLE_NOISE_MARKERS)


def _is_informative_risk(entry: RiskEntry) -> bool:
    """Whether an extracted entry contains usable risk information."""
    if entry.clause_text or entry.explanation or entry.suggestion:
        return True
    combined = f"{entry.title} {entry.source_excerpt}"
    return _contains_any(combined, RISK_HINT_MARKERS)


def _is_informative_for_final_applied(entry: RiskEntry) -> bool:
    """Stricter filter for final-applied files to avoid plain-clause false positives."""
    if _is_style_only_comment(entry.source_excerpt):
        return False
    if entry.explanation or entry.suggestion:
        return True
    combined = f"{entry.title} {entry.source_excerpt}"
    if "批注#" in combined:
        return True
    return _contains_any(
        combined,
        (
            "风险点",
            "问题说明",
            "修改建议",
            "修改理由",
            "审查意见",
        ),
    )


def _priority_for_third_party(path: Path) -> tuple[int, str]:
    name = path.parent.name
    full = str(path)
    if "审查意见书" in name or "审查意见书" in full:
        return (0, name)
    if "修订批注版" in name or "批注版" in name:
        return (1, name)
    if "修订版" in name:
        return (2, name)
    return (3, name)


def _signal_score(markdown_path: Path) -> int:
    try:
        text = read_text(markdown_path)
    except Exception:  # noqa: BLE001
        return 0
    return sum(text.count(marker) for marker in RISK_HINT_MARKERS)


def select_baseline_markdown(contract_dir: Path, participant: str) -> Path | None:
    """Select baseline markdown file by participant and priority.

    Args:
        contract_dir: Contract run directory under outputs_md/{run_id}.
        participant: `third_party` or `final_applied`.

    Returns:
        Selected markdown path, or None if missing.
    """
    if participant == "third_party":
        root = contract_dir / "2-第三方平台审查结果"
        if not root.exists():
            return None
        candidates = sorted(root.rglob("output.md"))
        if not candidates:
            return None
        ranked = sorted(candidates, key=_priority_for_third_party)
        return ranked[0]

    if participant == "final_applied":
        candidates = sorted(contract_dir.rglob("3-*最终审查意见*/output.md"))
        if not candidates:
            candidates = sorted(
                path
                for path in contract_dir.rglob("output.md")
                if "3-最终审查意见" in str(path.parent)
            )
        if not candidates:
            return None
        ranked = sorted(candidates, key=lambda path: (-_signal_score(path), len(str(path))))
        return ranked[0]

    msg = f"Unsupported participant: {participant}"
    raise ValueError(msg)


def _parse_table_fields(section_lines: list[str]) -> tuple[str, str, str]:
    clause_text = ""
    explanation = ""
    suggestion = ""

    tables = split_markdown_tables(section_lines)
    if not tables:
        return clause_text, explanation, suggestion

    rows = parse_markdown_table(tables[0])
    if not rows:
        return clause_text, explanation, suggestion

    clean_rows = [[clean_markdown_cell(cell) for cell in row] for row in rows]
    if len(clean_rows) >= 2 and "条款原文" in clean_rows[0][0]:
        row = clean_rows[1]
        clause_text = row[0] if len(row) >= 1 else ""
        suggestion = row[1] if len(row) >= 2 else ""

    for idx, row in enumerate(clean_rows):
        if row and "修改理由" in row[0] and idx + 1 < len(clean_rows):
            explanation = max(clean_rows[idx + 1], key=len)
            break

    return clause_text, explanation, suggestion


def _parse_numbered_section_entries(contract_id: str, markdown_text: str, prefix: str) -> list[RiskEntry]:
    risks: list[RiskEntry] = []
    for block in split_numbered_sections(markdown_text):
        clause_text, explanation, suggestion = _parse_table_fields(block.lines)
        section_text = "\n".join(block.lines)

        if not explanation:
            exp_match = re.search(r"(?:风险说明|问题说明|修改理由)[:：]\s*(.+)", section_text)
            explanation = compact_text(exp_match.group(1)) if exp_match else ""

        if not suggestion:
            sug_match = re.search(r"(?:修改建议|建议修改)[:：]\s*(.+)", section_text)
            suggestion = compact_text(sug_match.group(1)) if sug_match else ""

        source_excerpt = compact_text(" ".join(block.lines[:8]))
        entry = RiskEntry(
            risk_id=f"{contract_id}_{prefix}_sec_{block.index:03d}",
            contract_id=contract_id,
            title=block.title,
            clause_text=clause_text,
            explanation=explanation,
            suggestion=suggestion,
            source_excerpt=source_excerpt,
        )
        if not _is_informative_risk(entry):
            continue
        risks.append(entry)
    return risks


def _parse_inline_comment_entries(contract_id: str, markdown_text: str, prefix: str) -> list[RiskEntry]:
    risks: list[RiskEntry] = []
    lines = markdown_text.splitlines()
    index = 0

    comment_pattern = re.compile(r"【批注#\d+/[^:]+:\s*(.*?)】")
    risk_block_pattern = re.compile(
        r"【风险点】(?P<title>.*?)【说明】(?P<explanation>.*?)(?:【修改建议】(?P<suggestion>.*))?$"
    )

    for line in lines:
        for matched in comment_pattern.finditer(line):
            index += 1
            comment_text = compact_text(matched.group(1))
            if _is_style_only_comment(comment_text):
                continue
            title = ""
            explanation = ""
            suggestion = ""

            risk_block = risk_block_pattern.search(comment_text)
            if risk_block:
                title = compact_text(risk_block.group("title"))
                explanation = compact_text(risk_block.group("explanation"))
                suggestion = compact_text(risk_block.group("suggestion") or "")
            else:
                title = comment_text[:28] if comment_text else f"comment_{index}"
                explanation = comment_text

            clause_text = compact_text(comment_pattern.sub("", line))
            risks.append(
                RiskEntry(
                    risk_id=f"{contract_id}_{prefix}_cmt_{index:03d}",
                    contract_id=contract_id,
                    title=title,
                    clause_text=clause_text,
                    explanation=explanation,
                    suggestion=suggestion,
                    source_excerpt=comment_text,
                )
            )

    return risks


def _parse_structured_report_entries(contract_id: str, markdown_text: str, prefix: str) -> list[RiskEntry]:
    """Parse sections with `具体条款/风险说明/修改建议` fields."""
    risks: list[RiskEntry] = []

    pattern = re.compile(
        r"\*\*(?P<index>\d+)\.(?P<title>[^*]+?)\*\*(?P<body>.*?)(?=\n\*\*\d+\.|\Z)",
        flags=re.DOTALL,
    )

    for matched in pattern.finditer(markdown_text):
        body = matched.group("body")
        clause_match = re.search(r"具体条款[:：]\s*(.+?)\n\n", body, flags=re.DOTALL)
        exp_match = re.search(r"风险说明[:：]\s*(.+?)\n\n", body, flags=re.DOTALL)
        sug_match = re.search(r"修改建议[:：]\s*(.+?)\n\n", body, flags=re.DOTALL)

        entry = RiskEntry(
            risk_id=f"{contract_id}_{prefix}_rep_{int(matched.group('index')):03d}",
            contract_id=contract_id,
            title=compact_text(matched.group("title")),
            clause_text=compact_text(clause_match.group(1)) if clause_match else "",
            explanation=compact_text(exp_match.group(1)) if exp_match else "",
            suggestion=compact_text(sug_match.group(1)) if sug_match else "",
            source_excerpt=compact_text(body[:220]),
        )
        if not _is_informative_risk(entry):
            continue
        risks.append(entry)

    return risks


def _deduplicate(risks: list[RiskEntry]) -> list[RiskEntry]:
    dedup: list[RiskEntry] = []
    seen: set[str] = set()
    for item in risks:
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
        dedup.append(item)
    return dedup


def _filter_by_participant(participant: str, risks: list[RiskEntry]) -> list[RiskEntry]:
    if participant == "final_applied":
        return [item for item in risks if _is_informative_for_final_applied(item)]
    return [item for item in risks if _is_informative_risk(item)]


def parse_baseline_markdown(
    *,
    contract_id: str,
    participant: str,
    markdown_path: Path,
) -> list[RiskEntry]:
    """Parse baseline markdown into risk entries.

    Args:
        contract_id: Contract identifier.
        participant: `third_party`, `final_applied`, or `agent`.
        markdown_path: Baseline markdown path.

    Returns:
        Parsed risk list.
    """
    markdown_text = read_text(markdown_path)
    prefix = participant

    risks: list[RiskEntry] = []
    risks.extend(_parse_structured_report_entries(contract_id, markdown_text, prefix))
    risks.extend(_parse_numbered_section_entries(contract_id, markdown_text, prefix))
    risks.extend(_parse_inline_comment_entries(contract_id, markdown_text, prefix))

    return _deduplicate(_filter_by_participant(participant, risks))
