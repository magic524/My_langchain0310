"""从 DOCX 中抽取批注、样式与可见段落信息。"""

from __future__ import annotations

import traceback
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .common import WORD_NS, dedupe_nonempty_texts, normalize_whitespace


def paragraph_text(paragraph: ET.Element) -> str:
    """抽取段落里的可见文本。"""

    parts: list[str] = []
    for node in paragraph.findall(".//w:t", WORD_NS):
        if node.text:
            parts.append(node.text)
    return normalize_whitespace("".join(parts))


def extract_docx_visible_paragraphs(docx_path: Path) -> list[str]:
    """按阅读顺序抽取 `document.xml` 中的可见段落。"""

    if not docx_path.exists():
        return []

    try:
        with zipfile.ZipFile(docx_path) as archive:
            document_root = ET.fromstring(archive.read("word/document.xml"))
    except Exception:
        return []

    paragraphs: list[str] = []
    for paragraph in document_root.findall(".//w:p", WORD_NS):
        text = paragraph_text(paragraph)
        if text:
            paragraphs.append(text)
    return paragraphs


def find_ancestor(
    element: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    local_name: str,
) -> ET.Element | None:
    """向上查找指定标签名的祖先节点。"""

    current = parent_map.get(element)
    while current is not None:
        if current.tag.rsplit("}", 1)[-1] == local_name:
            return current
        current = parent_map.get(current)
    return None


def build_match_candidates(
    paragraph: ET.Element,
    paragraph_content: str,
    paragraph_index: int,
    paragraphs: list[ET.Element],
    parent_map: dict[ET.Element, ET.Element],
) -> list[str]:
    """为批注/样式构造更稳的匹配候选，兼顾表格与上下文。"""

    candidates: list[str] = [paragraph_content]

    previous_text = ""
    for prev_idx in range(paragraph_index - 2, -1, -1):
        previous_text = paragraph_text(paragraphs[prev_idx])
        if previous_text:
            break

    next_text = ""
    for next_idx in range(paragraph_index, len(paragraphs)):
        next_text = paragraph_text(paragraphs[next_idx])
        if next_text:
            break

    if previous_text:
        candidates.append(previous_text)
        candidates.append(f"{previous_text} {paragraph_content}")
    if next_text:
        candidates.append(next_text)
        candidates.append(f"{paragraph_content} {next_text}")
    if previous_text and next_text:
        candidates.append(f"{previous_text} {paragraph_content} {next_text}")

    table_cell = find_ancestor(paragraph, parent_map, "tc")
    if table_cell is not None:
        cell_text = " ".join(
            dedupe_nonempty_texts([paragraph_text(node) for node in table_cell.findall(".//w:p", WORD_NS)])
        )
        if cell_text:
            candidates.append(cell_text)
            if previous_text:
                candidates.append(f"{previous_text} {cell_text}")
            if next_text:
                candidates.append(f"{cell_text} {next_text}")

    table_row = find_ancestor(paragraph, parent_map, "tr")
    if table_row is not None:
        row_texts: list[str] = []
        for cell in table_row.findall("./w:tc", WORD_NS):
            row_texts.extend(
                dedupe_nonempty_texts([paragraph_text(node) for node in cell.findall(".//w:p", WORD_NS)])
            )
        row_text = " ".join(dedupe_nonempty_texts(row_texts))
        if row_text:
            candidates.append(row_text)
            if previous_text:
                candidates.append(f"{previous_text} {row_text}")
            if next_text:
                candidates.append(f"{row_text} {next_text}")

    return sorted(dedupe_nonempty_texts(candidates), key=len, reverse=True)


def extract_docx_comments_with_anchors(docx_path: Path) -> list[dict]:
    """抽取批注正文及其对应的原文锚点。"""

    if not docx_path.exists():
        return []

    try:
        with zipfile.ZipFile(docx_path) as archive:
            if "word/comments.xml" not in archive.namelist() or "word/document.xml" not in archive.namelist():
                return []

            comment_map: dict[str, dict] = {}
            comments_root = ET.fromstring(archive.read("word/comments.xml"))
            for comment in comments_root.findall(".//w:comment", WORD_NS):
                comment_id = comment.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                author = comment.attrib.get(f"{{{WORD_NS['w']}}}author", "未知作者")
                comment_text = " ".join(filter(None, (paragraph_text(p) for p in comment.findall(".//w:p", WORD_NS))))
                comment_map[comment_id] = {
                    "comment_id": comment_id,
                    "author": author,
                    "comment_text": normalize_whitespace(comment_text),
                }

            document_root = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = document_root.findall(".//w:p", WORD_NS)
            parent_map = {child: parent for parent in document_root.iter() for child in parent}
            anchors: list[dict] = []

            for index, paragraph in enumerate(paragraphs, start=1):
                paragraph_content = paragraph_text(paragraph)
                if not paragraph_content:
                    continue

                started_ids = [
                    node.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    for node in paragraph.findall(".//w:commentRangeStart", WORD_NS)
                ]
                reference_ids = [
                    node.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    for node in paragraph.findall(".//w:commentReference", WORD_NS)
                ]
                for comment_id in [cid for cid in {*(started_ids or []), *(reference_ids or [])} if cid]:
                    comment_payload = comment_map.get(
                        comment_id,
                        {
                            "comment_id": comment_id,
                            "author": "未知作者",
                            "comment_text": "",
                        },
                    )
                    anchors.append(
                        {
                            "comment_id": comment_payload["comment_id"],
                            "author": comment_payload["author"],
                            "comment_text": comment_payload["comment_text"],
                            "paragraph_index": index,
                            "paragraph_excerpt": paragraph_content[:180],
                            "match_candidates": build_match_candidates(
                                paragraph,
                                paragraph_content,
                                index,
                                paragraphs,
                                parent_map,
                            ),
                        }
                    )

            deduped: list[dict] = []
            seen: set[tuple[str, int]] = set()
            for item in anchors:
                key = (item["comment_id"], item["paragraph_index"])
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            return deduped
    except Exception:
        traceback.print_exc()
        return []


def extract_docx_style_hints(docx_path: Path) -> list[dict]:
    """抽取加粗、下划线、颜色等样式提示。"""

    if not docx_path.exists():
        return []

    hints: list[dict] = []
    try:
        with zipfile.ZipFile(docx_path) as archive:
            if "word/document.xml" not in archive.namelist():
                return []

            document_root = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = document_root.findall(".//w:p", WORD_NS)
            parent_map = {child: parent for parent in document_root.iter() for child in parent}

            for index, paragraph in enumerate(paragraphs, start=1):
                paragraph_content = paragraph_text(paragraph)
                if not paragraph_content:
                    continue

                styles: set[str] = set()
                colors: set[str] = set()
                for run in paragraph.findall(".//w:r", WORD_NS):
                    run_properties = run.find("w:rPr", WORD_NS)
                    if run_properties is None:
                        continue

                    if run_properties.find("w:i", WORD_NS) is not None:
                        styles.add("italic")

                    underline = run_properties.find("w:u", WORD_NS)
                    if underline is not None:
                        underline_value = underline.attrib.get(f"{{{WORD_NS['w']}}}val", "")
                        if not underline_value or underline_value.lower() != "none":
                            styles.add("underline")

                    color_node = run_properties.find("w:color", WORD_NS)
                    if color_node is not None:
                        color_value = color_node.attrib.get(f"{{{WORD_NS['w']}}}val", "")
                        if color_value and color_value.lower() not in {"auto", "000000"}:
                            colors.add(f"color#{color_value.upper()}")

                    highlight_node = run_properties.find("w:highlight", WORD_NS)
                    if highlight_node is not None:
                        highlight_value = highlight_node.attrib.get(f"{{{WORD_NS['w']}}}val", "")
                        if highlight_value and highlight_value.lower() != "none":
                            styles.add(f"highlight:{highlight_value}")

                # 加粗在 Docling 导出的 Markdown 中通常已经保留，这里只保留额外样式提示。
                tags = sorted([*styles, *colors])

                if not tags:
                    continue

                hints.append(
                    {
                        "paragraph_index": index,
                        "paragraph_excerpt": paragraph_content[:180],
                        "match_candidates": build_match_candidates(
                            paragraph,
                            paragraph_content,
                            index,
                            paragraphs,
                            parent_map,
                        ),
                        "style_tags": tags,
                    }
                )
    except Exception:
        traceback.print_exc()
        return []

    return hints
