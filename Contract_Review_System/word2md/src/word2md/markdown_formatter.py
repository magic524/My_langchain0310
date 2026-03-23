"""Markdown 后处理与批注注入。"""

from __future__ import annotations

import re

from .common import dedupe_nonempty_texts, normalize_whitespace


CHINESE_NUMS = [
    "零",
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
    "十一",
    "十二",
    "十三",
    "十四",
    "十五",
    "十六",
    "十七",
    "十八",
    "十九",
    "二十",
]


def chinese_num_to_int(token: str) -> int | None:
    """将中文数字标题转为整数。"""

    if token in CHINESE_NUMS:
        return CHINESE_NUMS.index(token)
    return None


def int_to_chinese_num(value: int) -> str:
    """将整数转回中文数字标题。"""

    if 1 <= value < len(CHINESE_NUMS):
        return CHINESE_NUMS[value]
    return str(value)


def postprocess_legal_markdown(md_text: str) -> str:
    """轻量修复 Docling 导出的合同 Markdown 结构。"""

    section_re = re.compile(r"^\s*\*\*([一二三四五六七八九十]+)、([^*]+)\*\*\s*$")
    bullet_bold_re = re.compile(r"^\s*-\s+\*\*([^*]+)\*\*\s*$")
    subsec_re = re.compile(r"^\s*\*\*[（(][一二三四五六七八九十]+[)）][^*]*\*\*\s*$")
    num_dot_re = re.compile(r"^\s*(\d+)\.\s+(.*)$")

    pass1: list[str] = []
    last_section_num: int | None = None
    for line in md_text.splitlines():
        sec_match = section_re.match(line)
        if sec_match:
            section_num = chinese_num_to_int(sec_match.group(1))
            if section_num is not None:
                last_section_num = section_num
            pass1.append(line.strip())
            continue

        bullet_match = bullet_bold_re.match(line)
        if bullet_match:
            title = bullet_match.group(1).strip()
            if title.startswith("（"):
                pass1.append(f"**{title}**")
                continue
            if last_section_num is not None:
                next_num = last_section_num + 1
                pass1.append(f"**{int_to_chinese_num(next_num)}、{title}**")
                last_section_num = next_num
            else:
                pass1.append(f"**{title}**")
            continue

        pass1.append(line)

    pass2: list[str] = []
    in_subsection = False
    subsection_index = 0
    for line in pass1:
        stripped = line.strip()
        if section_re.match(stripped):
            in_subsection = False
            subsection_index = 0
            pass2.append(stripped)
            continue

        if subsec_re.match(stripped):
            in_subsection = True
            subsection_index = 0
            pass2.append(stripped)
            continue

        num_match = num_dot_re.match(line)
        if num_match and in_subsection:
            subsection_index += 1
            pass2.append(f"{subsection_index}. {num_match.group(2).strip()}")
            continue

        if line.startswith("    "):
            if section_re.match(stripped) or subsec_re.match(stripped):
                pass2.append(stripped)
                continue
            if num_match:
                pass2.append(f"{num_match.group(1)}. {num_match.group(2).strip()}")
                continue

        pass2.append(line)

    pass3: list[str] = []
    first_major_heading_found = False
    major_heading_re = re.compile(r"^\*\*[一二三四五六七八九十]+、[^*]+\*\*$")
    sub_heading_re = re.compile(r"^\*\*[（(][一二三四五六七八九十]+[)）][^*]*\*\*$")
    for index, raw_line in enumerate(pass2):
        line = raw_line.rstrip()
        if line.startswith("    ") and not line.lstrip().startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5.", "|")):
            line = line.lstrip()
        if "<!-- image -->" in line:
            line = "<!-- image -->"

        stripped = line.strip()
        if not stripped:
            pass3.append("")
            continue

        if not first_major_heading_found and index <= 20:
            if stripped.startswith("**") and stripped.endswith("**") and "协议" in stripped and len(stripped) <= 60:
                title_text = stripped[2:-2].strip()
                if title_text:
                    line = f"# {title_text}"
                    stripped = line
            elif "协议" in stripped and len(stripped) <= 50 and not stripped.startswith("#"):
                line = f"# {stripped}"
                stripped = line

            if stripped.startswith("# ") or major_heading_re.match(stripped):
                first_major_heading_found = True

        if major_heading_re.match(stripped) or sub_heading_re.match(stripped) or stripped.startswith("# "):
            if pass3 and pass3[-1] != "":
                pass3.append("")
            pass3.append(stripped)
            pass3.append("")
            continue

        if stripped == "<!-- image -->":
            if pass3 and pass3[-1] != "":
                pass3.append("")
            pass3.append(stripped)
            pass3.append("")
            continue

        pass3.append(line)

    compact: list[str] = []
    blank_run = 0
    for line in pass3:
        if not line.strip():
            blank_run += 1
            if blank_run <= 1:
                compact.append("")
            continue
        blank_run = 0
        compact.append(line)

    output = "\n".join(compact)
    if md_text.endswith("\n"):
        output += "\n"
    return output


def normalize_for_match(text: str) -> str:
    """将原文段落与 Markdown 行归一化，便于模糊匹配。"""

    normalized = text.replace("\\_", "_")
    normalized = re.sub(r"[`*_>#|\-]+", "", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def extract_clause_key(text: str) -> str | None:
    """抽取条款编号，如 `5`、`5.1`、`5.2`。"""

    normalized = text.strip().translate(
        str.maketrans({"．": ".", "。": ".", "｡": ".", "﹒": ".", "、": ".", "（": "(", "）": ")"})
    )
    normalized = re.sub(r"\s+", "", normalized)

    sub_clause_match = re.match(r"^(\d+)\.(\d+)", normalized)
    if sub_clause_match:
        return f"{sub_clause_match.group(1)}.{sub_clause_match.group(2)}"

    clause_match = re.match(r"^(\d+)\.(?!\d)", normalized)
    if clause_match:
        return clause_match.group(1)

    return None


def find_line_index_for_excerpt(lines: list[str], excerpt: str, start_idx: int = 0) -> int | None:
    """根据段落片段在 Markdown 中查找最接近的行。"""

    normalized_excerpt = normalize_for_match(excerpt)
    if len(normalized_excerpt) < 6:
        return None

    fragment_candidates = [normalized_excerpt[:40], normalized_excerpt[:28], normalized_excerpt[:18], normalized_excerpt[:12]]
    fragment_candidates = [fragment for fragment in fragment_candidates if len(fragment) >= 8]
    if not fragment_candidates:
        return None

    for index in range(start_idx, len(lines)):
        line_norm = normalize_for_match(lines[index])
        if len(line_norm) >= 4 and any(fragment in line_norm for fragment in fragment_candidates):
            return index

    for index in range(0, start_idx):
        line_norm = normalize_for_match(lines[index])
        if len(line_norm) >= 4 and any(fragment in line_norm for fragment in fragment_candidates):
            return index

    return None


def find_line_index_for_clause_key(lines: list[str], clause_key: str, start_idx: int = 0) -> int | None:
    """根据条款编号定位 Markdown 行。"""

    if not clause_key:
        return None

    for index in range(start_idx, len(lines)):
        if extract_clause_key(lines[index]) == clause_key:
            return index

    for index in range(0, start_idx):
        if extract_clause_key(lines[index]) == clause_key:
            return index

    return None


def find_line_index_for_candidates(
    lines: list[str],
    match_candidates: list[str],
    fallback_excerpt: str,
    start_idx: int = 0,
) -> int | None:
    """优先用原段落匹配，必要时再回退到上下文候选。"""

    fallback_clause_key = extract_clause_key(fallback_excerpt)
    if fallback_excerpt:
        matched_index = find_line_index_for_excerpt(lines, fallback_excerpt, start_idx=start_idx)
        if matched_index is not None:
            return matched_index
        matched_index = find_line_index_for_clause_key(lines, fallback_clause_key or "", start_idx=start_idx)
        if matched_index is not None:
            return matched_index

    ordered_candidates: list[str] = []
    fallback_norm = normalize_whitespace(fallback_excerpt)
    for candidate in dedupe_nonempty_texts(match_candidates):
        if fallback_norm and normalize_whitespace(candidate) == fallback_norm:
            continue
        ordered_candidates.append(candidate)

    if fallback_clause_key:
        same_clause_candidates = [
            candidate for candidate in ordered_candidates if extract_clause_key(candidate) == fallback_clause_key
        ]
        other_candidates = [
            candidate for candidate in ordered_candidates if extract_clause_key(candidate) != fallback_clause_key
        ]
        ordered_candidates = same_clause_candidates + other_candidates

    for candidate in ordered_candidates:
        matched_index = find_line_index_for_excerpt(lines, candidate, start_idx=start_idx)
        if matched_index is None:
            continue
        line_clause_key = extract_clause_key(lines[matched_index])
        candidate_clause_key = extract_clause_key(candidate)
        if fallback_clause_key and line_clause_key and line_clause_key != fallback_clause_key:
            continue
        if fallback_clause_key and candidate_clause_key and candidate_clause_key != fallback_clause_key:
            continue
        return matched_index

    if fallback_clause_key:
        return find_line_index_for_clause_key(lines, fallback_clause_key, start_idx=start_idx)

    return None


def repair_missing_numbered_paragraphs(md_text: str, source_paragraphs: list[str]) -> tuple[str, dict]:
    """用原始 DOCX 段落补齐 Docling 漏掉的编号条款。"""

    if not md_text or not source_paragraphs:
        return md_text, {"inserted_count": 0}

    numbered_re = re.compile(r"^(?:[一二三四五六七八九十]+、|\d+、|\d+\.\d+|[（(][一二三四五六七八九十0-9]+[)）])")
    lines = md_text.splitlines()
    present = {normalize_for_match(line) for line in lines if normalize_for_match(line)}

    def find_broken_line_index(paragraph: str) -> int | None:
        top_match = re.match(r"^(\d+)、(.+)$", paragraph)
        if top_match:
            number = top_match.group(1)
            text_only = top_match.group(2).strip()
            for idx, line in enumerate(lines):
                stripped = line.strip()
                if stripped == f"{number}、" or stripped == text_only:
                    return idx

        sub_match = re.match(r"^(\d+)\.(\d+)\s*(.+)$", paragraph)
        if sub_match:
            sub_number = sub_match.group(2)
            text_only = sub_match.group(3).strip()
            for idx, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith(f".{sub_number}") or stripped == text_only:
                    return idx
        return None

    source_matches: list[tuple[str, int | None]] = []
    search_cursor = 0
    for paragraph in source_paragraphs:
        matched_index = find_line_index_for_excerpt(lines, paragraph, start_idx=search_cursor)
        source_matches.append((paragraph, matched_index))
        if matched_index is not None:
            search_cursor = matched_index

    inserts: dict[int, list[str]] = {}
    inserted_count = 0
    for index, (paragraph, line_index) in enumerate(source_matches):
        normalized = normalize_for_match(paragraph)
        if line_index is not None or not normalized or normalized in present:
            continue
        if not numbered_re.match(paragraph):
            continue

        broken_index = find_broken_line_index(paragraph)
        if broken_index is not None:
            lines[broken_index] = paragraph
            source_matches[index] = (paragraph, broken_index)
            present.add(normalized)
            inserted_count += 1
            continue

        insert_at: int | None = None
        for prev_index in range(index - 1, -1, -1):
            previous_line_index = source_matches[prev_index][1]
            if previous_line_index is not None:
                insert_at = previous_line_index + 1
                break
        if insert_at is None:
            for next_index in range(index + 1, len(source_matches)):
                next_line_index = source_matches[next_index][1]
                if next_line_index is not None:
                    insert_at = next_line_index
                    break
        if insert_at is None:
            continue

        inserts.setdefault(insert_at, []).append(paragraph)
        present.add(normalized)
        inserted_count += 1

    if not inserts:
        return md_text, {"inserted_count": 0}

    merged_lines: list[str] = []
    for index, line in enumerate(lines):
        if index in inserts:
            merged_lines.extend(inserts[index])
        merged_lines.append(line)
    if len(lines) in inserts:
        merged_lines.extend(inserts[len(lines)])

    merged_text = "\n".join(merged_lines)
    if md_text.endswith("\n"):
        merged_text += "\n"
    return merged_text, {"inserted_count": inserted_count}


def inject_inline_annotations(md_text: str, comment_anchors: list[dict], style_hints: list[dict]) -> tuple[str, dict]:
    """将批注与样式提示注入到命中的 Markdown 行末尾。"""

    lines = md_text.splitlines()
    if not lines:
        return md_text, {
            "comment_matched": 0,
            "comment_unmatched": len(comment_anchors),
            "style_matched": 0,
            "style_unmatched": len(style_hints),
        }

    line_comment_payloads: dict[int, list[str]] = {}
    line_style_payloads: dict[int, list[str]] = {}
    comment_matched = 0
    style_matched = 0

    cursor = 0
    for item in sorted(comment_anchors, key=lambda data: (data.get("paragraph_index", 0), str(data.get("comment_id", "")))):
        line_index = find_line_index_for_candidates(
            lines,
            list(item.get("match_candidates", []) or []),
            str(item.get("paragraph_excerpt", "")),
            start_idx=cursor,
        )
        if line_index is None:
            continue
        comment_id = item.get("comment_id", "")
        author = item.get("author", "未知作者")
        paragraph_index = item.get("paragraph_index", "?")
        comment_text = (item.get("comment_text", "") or "（批注正文为空）").strip()
        marker = f"批注#{comment_id}/段落{paragraph_index}/作者{author}: {comment_text}"
        line_comment_payloads.setdefault(line_index, []).append(marker)
        comment_matched += 1
        cursor = line_index

    cursor = 0
    for item in sorted(style_hints, key=lambda data: int(data.get("paragraph_index", 0))):
        line_index = find_line_index_for_candidates(
            lines,
            list(item.get("match_candidates", []) or []),
            str(item.get("paragraph_excerpt", "")),
            start_idx=cursor,
        )
        if line_index is None:
            continue
        style_tags = item.get("style_tags", [])
        if not style_tags:
            continue
        paragraph_index = item.get("paragraph_index", "?")
        marker = f"样式/段落{paragraph_index}: {', '.join(style_tags)}"
        line_style_payloads.setdefault(line_index, []).append(marker)
        style_matched += 1
        cursor = line_index

    if not line_comment_payloads and not line_style_payloads:
        return md_text, {
            "comment_matched": 0,
            "comment_unmatched": len(comment_anchors),
            "style_matched": 0,
            "style_unmatched": len(style_hints),
        }

    new_lines: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        payloads: list[str] = []
        payloads.extend(line_comment_payloads.get(index, []))
        payloads.extend(line_style_payloads.get(index, []))

        if payloads:
            joined_payload = "；".join(payloads)
            if stripped.startswith("|") and stripped.endswith("|"):
                new_lines.append(line)
                new_lines.append(f"【{joined_payload}】")
                continue
            if stripped and not stripped.startswith("<!--"):
                line = f"{line}【{joined_payload}】"

        new_lines.append(line)

    enriched_text = "\n".join(new_lines)
    if md_text.endswith("\n"):
        enriched_text += "\n"
    return enriched_text, {
        "comment_matched": comment_matched,
        "comment_unmatched": max(len(comment_anchors) - comment_matched, 0),
        "style_matched": style_matched,
        "style_unmatched": max(len(style_hints) - style_matched, 0),
    }
