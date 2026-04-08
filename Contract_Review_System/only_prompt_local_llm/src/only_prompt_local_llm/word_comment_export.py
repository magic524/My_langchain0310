from __future__ import annotations

import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

DOCX_PREFIXES = {
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "o": "urn:schemas-microsoft-com:office:office",
    "r": REL_NS,
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "v": "urn:schemas-microsoft-com:vml",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "w": WORD_NS,
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpsCustomData": "http://www.wps.cn/officeDocument/2013/wpsCustomData",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
DOCUMENT_ROOT_RE = re.compile(r"<w:document\b[^>]*>", re.IGNORECASE)
MISSING_CLAUSE_MARKERS = (
    "全文未涉及",
    "全文未约定",
    "全文未提及",
    "未涉及相关约定",
    "未约定相关条款",
)
NORMALIZE_TRANSLATION = str.maketrans(
    {
        "\r": " ",
        "\n": " ",
        "\u3000": " ",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "：": ":",
        "；": ";",
        "，": ",",
        "。": ".",
        "、": ".",
    }
)

ET.register_namespace("w", WORD_NS)
ET.register_namespace("r", REL_NS)
for prefix, uri in DOCX_PREFIXES.items():
    ET.register_namespace(prefix, uri)


def _w_tag(local_name: str) -> str:
    return f"{{{WORD_NS}}}{local_name}"


def _r_tag(local_name: str) -> str:
    return f"{{{REL_NS}}}{local_name}"


def _pkg_rel_tag(local_name: str) -> str:
    return f"{{{PKG_REL_NS}}}{local_name}"


def _content_type_tag(local_name: str) -> str:
    return f"{{{CONTENT_TYPE_NS}}}{local_name}"


@dataclass(slots=True)
class ParagraphRecord:
    index: int
    text: str
    normalized_text: str
    element: ET.Element
    match_candidates: list[str]


@dataclass(slots=True)
class AnchorMatch:
    start_index: int
    end_index: int
    matched_text: str
    strategy: str
    score: int


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy clause matching."""

    normalized = str(text).translate(NORMALIZE_TRANSLATION)
    normalized = normalized.replace("\\_", "_")
    normalized = re.sub(r"[_＿]{2,}", " ", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip()


def paragraph_text(paragraph: ET.Element) -> str:
    """Return visible paragraph text from a WordprocessingML paragraph."""

    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == _w_tag("t") and node.text:
            parts.append(node.text)
        elif node.tag in {_w_tag("tab"), _w_tag("br"), _w_tag("cr")}:
            parts.append(" ")
    return normalize_text("".join(parts))


def _dedupe_nonempty_texts(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_text(value)
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def _find_ancestor(element: ET.Element, parent_map: dict[ET.Element, ET.Element], local_name: str) -> ET.Element | None:
    current = parent_map.get(element)
    while current is not None:
        if current.tag.rsplit("}", 1)[-1] == local_name:
            return current
        current = parent_map.get(current)
    return None


def _build_match_candidates(
    paragraph: ET.Element,
    paragraph_content: str,
    paragraph_position: int,
    paragraph_elements: list[ET.Element],
    paragraph_texts: list[str],
    parent_map: dict[ET.Element, ET.Element],
) -> list[str]:
    candidates: list[str] = [paragraph_content]

    previous_text = ""
    for prev_idx in range(paragraph_position - 1, -1, -1):
        previous_text = paragraph_texts[prev_idx]
        if previous_text:
            break

    next_text = ""
    for next_idx in range(paragraph_position + 1, len(paragraph_elements)):
        next_text = paragraph_texts[next_idx]
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

    table_cell = _find_ancestor(paragraph, parent_map, "tc")
    if table_cell is not None:
        cell_text = " ".join(
            _dedupe_nonempty_texts([paragraph_text(node) for node in table_cell.findall(".//w:p", {"w": WORD_NS})])
        )
        if cell_text:
            candidates.append(cell_text)
            if previous_text:
                candidates.append(f"{previous_text} {cell_text}")
            if next_text:
                candidates.append(f"{cell_text} {next_text}")

    table_row = _find_ancestor(paragraph, parent_map, "tr")
    if table_row is not None:
        row_texts: list[str] = []
        for cell in table_row.findall("./w:tc", {"w": WORD_NS}):
            row_texts.extend(_dedupe_nonempty_texts([paragraph_text(node) for node in cell.findall(".//w:p", {"w": WORD_NS})]))
        row_text = " ".join(_dedupe_nonempty_texts(row_texts))
        if row_text:
            candidates.append(row_text)
            if previous_text:
                candidates.append(f"{previous_text} {row_text}")
            if next_text:
                candidates.append(f"{row_text} {next_text}")

    return sorted(_dedupe_nonempty_texts(candidates), key=len, reverse=True)


def extract_paragraphs(document_root: ET.Element) -> list[ParagraphRecord]:
    """Extract non-empty paragraphs in reading order with fuzzy-match candidates."""

    paragraph_elements = document_root.findall(".//w:p", {"w": WORD_NS})
    paragraph_texts = [paragraph_text(element) for element in paragraph_elements]
    parent_map = {child: parent for parent in document_root.iter() for child in parent}

    records: list[ParagraphRecord] = []
    for paragraph_position, element in enumerate(paragraph_elements):
        text = paragraph_texts[paragraph_position]
        if not text:
            continue
        records.append(
            ParagraphRecord(
                index=len(records) + 1,
                text=text,
                normalized_text=normalize_text(text),
                element=element,
                match_candidates=_build_match_candidates(
                    element,
                    text,
                    paragraph_position,
                    paragraph_elements,
                    paragraph_texts,
                    parent_map,
                ),
            )
        )
    return records


def _split_match_segments(clause_text: str) -> list[str]:
    normalized = normalize_text(clause_text)
    if not normalized:
        return []
    if any(marker in normalized for marker in MISSING_CLAUSE_MARKERS):
        return []

    raw_segments = re.split(r"(?:\.{3,}|…+|；|;|\|)", normalized)
    segments: list[str] = []
    for segment in raw_segments:
        cleaned = normalize_text(segment)
        cleaned = re.sub(r"^[第条款章节一二三四五六七八九十百千0-9.()\[\] ]+", "", cleaned)
        cleaned = cleaned.strip(" :;,.()[]")
        if len(cleaned) >= 4:
            segments.append(cleaned)

    if not segments and normalized:
        segments.append(normalized)
    return segments


def _score_candidate_text(candidate_text: str, search_text: str) -> int:
    normalized_candidate = normalize_text(candidate_text)
    normalized_search = normalize_text(search_text)
    if not normalized_search:
        return 0

    score = 0
    if normalized_search in normalized_candidate:
        score += 1000 + len(normalized_search)
    for segment in _split_match_segments(normalized_search):
        if segment in normalized_candidate:
            score += 100 + len(segment)
    return score


def find_best_anchor(paragraphs: list[ParagraphRecord], clause_text: str) -> AnchorMatch:
    """Find the best paragraph window for a clause reference."""

    if not paragraphs:
        raise ValueError("No paragraphs available for anchoring")

    normalized_clause = normalize_text(clause_text)
    if not normalized_clause or any(marker in normalized_clause for marker in MISSING_CLAUSE_MARKERS):
        first = max(
            [paragraph for paragraph in paragraphs if paragraph.index != 1 and len(paragraph.normalized_text) >= 8] or paragraphs,
            key=lambda item: len(item.normalized_text),
        )
        return AnchorMatch(
            start_index=first.index,
            end_index=first.index,
            matched_text=first.text,
            strategy="document_fallback",
            score=0,
        )

    best: AnchorMatch | None = None

    for paragraph in paragraphs:
        for candidate_text in paragraph.match_candidates:
            score = _score_candidate_text(candidate_text, normalized_clause)
            if score == 0:
                continue

            strategy = "candidate_match"
            if normalized_clause and normalized_clause in normalize_text(candidate_text):
                strategy = "direct_clause_match"
            elif candidate_text != paragraph.text:
                strategy = "context_or_table_match"

            candidate = AnchorMatch(
                start_index=paragraph.index,
                end_index=paragraph.index,
                matched_text=paragraph.text,
                strategy=strategy,
                score=score,
            )
            if best is None or candidate.score > best.score or (
                candidate.score == best.score and len(paragraph.text) > len(best.matched_text)
            ):
                best = candidate

    if best is not None:
        return best

    longest = max(paragraphs, key=lambda item: len(item.normalized_text))
    return AnchorMatch(
        start_index=longest.index,
        end_index=longest.index,
        matched_text=longest.text,
        strategy="longest_paragraph_fallback",
        score=0,
    )


def _load_meta_candidates(meta_path: Path) -> dict[int, list[str]]:
    if not meta_path.exists():
        return {}

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    candidates_by_index: dict[int, list[str]] = {}
    for key in ("style_hints", "comment_anchors"):
        for item in payload.get(key, []):
            if not isinstance(item, dict):
                continue
            paragraph_index = int(item.get("paragraph_index", 0) or 0)
            if paragraph_index <= 0:
                continue
            match_candidates = [str(value) for value in item.get("match_candidates", []) if str(value).strip()]
            if match_candidates:
                candidates_by_index.setdefault(paragraph_index, []).extend(match_candidates)
            excerpt = str(item.get("paragraph_excerpt", "")).strip()
            if excerpt:
                candidates_by_index.setdefault(paragraph_index, []).append(excerpt)

    return {index: _dedupe_nonempty_texts(values) for index, values in candidates_by_index.items()}


def _merge_meta_candidates(paragraphs: list[ParagraphRecord], meta_candidates: dict[int, list[str]]) -> None:
    for paragraph in paragraphs:
        extra = meta_candidates.get(paragraph.index)
        if not extra:
            continue
        paragraph.match_candidates = sorted(
            _dedupe_nonempty_texts([*paragraph.match_candidates, *extra]),
            key=len,
            reverse=True,
        )


def _score_clause_for_risk(clause: dict[str, Any], risk: dict[str, Any]) -> int:
    clause_text = normalize_text(str(clause.get("clause_text", "")))
    context_text = normalize_text(str(clause.get("context_text", "")))
    clause_title = normalize_text(str(clause.get("clause_title", "")))
    risk_clause = normalize_text(str(risk.get("clause_text", "")))
    risk_title = normalize_text(str(risk.get("title", "")))

    score = 0
    if risk_clause:
        score += _score_candidate_text(clause_text, risk_clause)
        score += _score_candidate_text(context_text, risk_clause) // 10
    if risk_title and risk_title in clause_title:
        score += 50 + len(risk_title)
    if risk_title and risk_title in context_text:
        score += 25 + len(risk_title)
    return score


def _build_anchor_texts(contract: dict[str, Any], risk: dict[str, Any]) -> list[str]:
    risk_clause_text = str(risk.get("clause_text", ""))
    clause_parts = [part.strip() for part in re.split(r"[\r\n]+", risk_clause_text) if part.strip()]
    anchor_texts = _dedupe_nonempty_texts([risk_clause_text, *clause_parts])

    source_excerpt = str(risk.get("source_excerpt", "")).strip()
    if source_excerpt and "Thinking Process" not in source_excerpt:
        excerpt_match = re.search(
            r"具体条款[:：]\s*(.*?)(?:风险说明[:：]|修改建议[:：]|$)",
            normalize_text(source_excerpt),
        )
        if excerpt_match is not None:
            anchor_texts = _dedupe_nonempty_texts([excerpt_match.group(1), *anchor_texts])

    scored_clauses: list[tuple[int, dict[str, Any]]] = []
    for clause in contract.get("clauses", []):
        if not isinstance(clause, dict):
            continue
        score = _score_clause_for_risk(clause, risk)
        if score > 0:
            scored_clauses.append((score, clause))

    scored_clauses.sort(
        key=lambda item: (
            item[0],
            len(normalize_text(str(item[1].get("clause_text", "")))),
        ),
        reverse=True,
    )

    for _, clause in scored_clauses[:1]:
        anchor_texts = _dedupe_nonempty_texts(
            [
                *anchor_texts,
                str(clause.get("clause_text", "")),
                str(clause.get("context_text", "")),
                str(clause.get("clause_title", "")),
            ]
        )

    if not anchor_texts:
        anchor_texts = [str(risk.get("title", ""))]
    return anchor_texts


def _make_comment_body(risk: dict[str, Any]) -> str:
    lines = [f"风险点：{risk.get('title', '').strip()}"]
    explanation = str(risk.get("explanation", "")).strip()
    suggestion = str(risk.get("suggestion", "")).strip()
    clause_text = str(risk.get("clause_text", "")).strip()

    if explanation:
        lines.append(f"说明：{explanation}")
    if suggestion:
        lines.append(f"建议：{suggestion}")
    if clause_text:
        lines.append(f"定位：{clause_text}")
    return "\n".join(lines)


def _preserve_document_root(serialized_xml: bytes, original_xml: bytes) -> bytes:
    """Reuse the original document root tag to preserve namespace declarations."""

    serialized_text = serialized_xml.decode("utf-8")
    original_text = original_xml.decode("utf-8")

    serialized_match = DOCUMENT_ROOT_RE.search(serialized_text)
    original_match = DOCUMENT_ROOT_RE.search(original_text)
    if serialized_match is None or original_match is None:
        return serialized_xml

    return f"{original_text[:original_match.end()]}{serialized_text[serialized_match.end():]}".encode("utf-8")


def _ensure_comments_relationship(rels_root: ET.Element) -> str:
    for relationship in rels_root.findall(_pkg_rel_tag("Relationship")):
        if relationship.attrib.get("Type") == COMMENTS_REL_TYPE:
            return relationship.attrib["Id"]

    existing_ids = [relationship.attrib.get("Id", "") for relationship in rels_root.findall(_pkg_rel_tag("Relationship"))]
    next_index = 1
    while f"rId{next_index}" in existing_ids:
        next_index += 1

    relationship = ET.Element(
        _pkg_rel_tag("Relationship"),
        {
            "Id": f"rId{next_index}",
            "Type": COMMENTS_REL_TYPE,
            "Target": "comments.xml",
        },
    )
    rels_root.append(relationship)
    return relationship.attrib["Id"]


def _ensure_comments_content_type(content_types_root: ET.Element) -> None:
    for override in content_types_root.findall(_content_type_tag("Override")):
        if override.attrib.get("PartName") == "/word/comments.xml":
            return

    content_types_root.append(
        ET.Element(
            _content_type_tag("Override"),
            {
                "PartName": "/word/comments.xml",
                "ContentType": COMMENTS_CONTENT_TYPE,
            },
        )
    )


def _comment_reference_run(comment_id: int) -> ET.Element:
    run = ET.Element(_w_tag("r"))
    run_properties = ET.SubElement(run, _w_tag("rPr"))
    ET.SubElement(run_properties, _w_tag("rStyle"), {_w_tag("val"): "CommentReference"})
    ET.SubElement(run, _w_tag("commentReference"), {_w_tag("id"): str(comment_id)})
    return run


def _comment_element(comment_id: int, body: str, author: str) -> ET.Element:
    comment = ET.Element(
        _w_tag("comment"),
        {
            _w_tag("id"): str(comment_id),
            _w_tag("author"): author,
            _w_tag("initials"): "LLM",
            _w_tag("date"): datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
    )
    for line in body.splitlines():
        paragraph = ET.SubElement(comment, _w_tag("p"))
        run = ET.SubElement(paragraph, _w_tag("r"))
        text_node = ET.SubElement(run, _w_tag("t"))
        text_node.text = line
    return comment


def _comment_id_sequence(comments_root: ET.Element) -> int:
    ids = []
    for comment in comments_root.findall(_w_tag("comment")):
        raw_value = comment.attrib.get(_w_tag("id")) or comment.attrib.get("id")
        if raw_value is None:
            continue
        try:
            ids.append(int(raw_value))
        except ValueError:
            continue
    return max(ids, default=-1) + 1


def _insert_range_markers(paragraphs_by_index: dict[int, ParagraphRecord], match: AnchorMatch, comment_id: int) -> None:
    start_paragraph = paragraphs_by_index[match.start_index].element
    end_paragraph = paragraphs_by_index[match.end_index].element

    start_marker = ET.Element(_w_tag("commentRangeStart"), {_w_tag("id"): str(comment_id)})
    end_marker = ET.Element(_w_tag("commentRangeEnd"), {_w_tag("id"): str(comment_id)})

    start_insert_at = 0
    if list(start_paragraph) and list(start_paragraph)[0].tag == _w_tag("pPr"):
        start_insert_at = 1
    start_paragraph.insert(start_insert_at, start_marker)

    end_paragraph.append(end_marker)
    end_paragraph.append(_comment_reference_run(comment_id))


def _xml_paragraph(text: str, *, style: str | None = None) -> str:
    escaped_text = escape(text)
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{style_xml}<w:r><w:t xml:space="preserve">{escaped_text}</w:t></w:r></w:p>'


def _parse_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_markdown_table_separator(line: str) -> bool:
    cells = _parse_markdown_table_row(line)
    if not cells:
        return False
    for cell in cells:
        raw = cell.replace(":", "").strip()
        if len(raw) < 3 or set(raw) != {"-"}:
            return False
    return True


def _xml_table(rows: list[list[str]]) -> str:
    row_xml: list[str] = []
    for row in rows:
        cell_xml = "".join(
            f'<w:tc><w:tcPr/><w:p><w:r><w:t xml:space="preserve">{escape(cell)}</w:t></w:r></w:p></w:tc>'
            for cell in row
        )
        row_xml.append(f"<w:tr>{cell_xml}</w:tr>")
    return "<w:tbl><w:tblPr/><w:tblGrid/>" + "".join(row_xml) + "</w:tbl>"


def build_docx_from_markdown(markdown_path: Path, destination_docx: Path, *, title: str) -> Path:
    """根据 Markdown 生成一份可批注的结构化 docx。"""

    markdown_text = markdown_path.read_text(encoding="utf-8")
    lines = markdown_text.splitlines()
    blocks: list[str] = [_xml_paragraph(title, style="Heading1")]
    index = 0

    # PDF 无法直接写回原文批注时，退化为一份结构化审查底稿。
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and _is_markdown_table_separator(lines[index + 1]):
            table_rows = [_parse_markdown_table_row(stripped)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_rows.append(_parse_markdown_table_row(lines[index]))
                index += 1
            blocks.append(_xml_table(table_rows))
            continue

        if stripped == "---":
            blocks.append(_xml_paragraph("----------"))
            index += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match is not None:
            level = min(len(heading_match.group(1)), 3)
            blocks.append(_xml_paragraph(heading_match.group(2).strip(), style=f"Heading{level}"))
            index += 1
            continue

        text = stripped
        if stripped.startswith(("- ", "* ")):
            text = f"• {stripped[2:].strip()}"
        blocks.append(_xml_paragraph(text))
        index += 1

    document_xml = "".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
            "<w:body>",
            *blocks,
            (
                '<w:sectPr>'
                '<w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" '
                'w:header="851" w:footer="992" w:gutter="0"/>'
                "</w:sectPr>"
            ),
            "</w:body>",
            "</w:document>",
        ]
    )
    package_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    document_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults>'
        '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="宋体"/>'
        '<w:sz w:val="22"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr/></w:pPrDefault>'
        '</w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/>'
        '<w:qFormat/>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        '<w:name w:val="heading 1"/>'
        '<w:basedOn w:val="Normal"/>'
        '<w:uiPriority w:val="9"/>'
        '<w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2">'
        '<w:name w:val="heading 2"/>'
        '<w:basedOn w:val="Normal"/>'
        '<w:uiPriority w:val="9"/>'
        '<w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="28"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading3">'
        '<w:name w:val="heading 3"/>'
        '<w:basedOn w:val="Normal"/>'
        '<w:uiPriority w:val="9"/>'
        '<w:qFormat/>'
        '<w:rPr><w:b/><w:sz w:val="24"/></w:rPr>'
        '</w:style>'
        "</w:styles>"
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Microsoft Office Word</Application>'
        '</Properties>'
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title)}</dc:title>"
        "<dc:creator>Contract Review System</dc:creator>"
        "<cp:lastModifiedBy>Contract Review System</cp:lastModifiedBy>"
        "</cp:coreProperties>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )

    destination_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination_docx, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", package_rels_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels_xml)
        archive.writestr("word/styles.xml", styles_xml)
    return destination_docx


def _is_valid_synthesized_docx(docx_path: Path) -> bool:
    """Check whether a synthesized docx contains the minimum Word package parts."""

    if not docx_path.exists():
        return False
    try:
        with zipfile.ZipFile(docx_path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return False

    required_parts = {
        "[Content_Types].xml",
        "_rels/.rels",
        "docProps/app.xml",
        "docProps/core.xml",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
    }
    return required_parts.issubset(names)


def annotate_docx_with_comments(
    source_docx: Path,
    destination_docx: Path,
    risks: list[dict[str, Any]],
    *,
    author: str = "local_llm",
    contract: dict[str, Any] | None = None,
    meta_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Copy a docx and inject Word comments for the provided risks."""

    shutil.copy2(source_docx, destination_docx)

    with zipfile.ZipFile(destination_docx, "r") as archive:
        payloads = {info.filename: archive.read(info.filename) for info in archive.infolist()}
        infos = {info.filename: info for info in archive.infolist()}
    original_document_xml = payloads["word/document.xml"]

    document_root = ET.fromstring(payloads["word/document.xml"])
    rels_root = ET.fromstring(
        payloads.get(
            "word/_rels/document.xml.rels",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
        )
    )
    content_types_root = ET.fromstring(payloads["[Content_Types].xml"])

    comments_root = ET.fromstring(
        payloads.get(
            "word/comments.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments xmlns:w="{WORD_NS}"/>'.encode("utf-8"),
        )
    )

    _ensure_comments_relationship(rels_root)
    _ensure_comments_content_type(content_types_root)

    paragraphs = extract_paragraphs(document_root)
    if meta_path is not None:
        _merge_meta_candidates(paragraphs, _load_meta_candidates(meta_path))
    paragraphs_by_index = {item.index: item for item in paragraphs}
    next_comment_id = _comment_id_sequence(comments_root)

    summary: list[dict[str, Any]] = []
    for risk in risks:
        anchor_texts = _build_anchor_texts(contract or {}, risk)
        match_candidates = [find_best_anchor(paragraphs, text) for text in anchor_texts]
        match = max(match_candidates, key=lambda item: item.score)
        comment_id = next_comment_id
        next_comment_id += 1

        _insert_range_markers(paragraphs_by_index, match, comment_id)
        comments_root.append(_comment_element(comment_id, _make_comment_body(risk), author))

        summary.append(
            {
                "risk_id": risk.get("risk_id", ""),
                "title": risk.get("title", ""),
                "start_paragraph_index": match.start_index,
                "end_paragraph_index": match.end_index,
                "matched_text": match.matched_text,
                "anchor_strategy": match.strategy,
                "score": match.score,
            }
        )

    payloads["word/document.xml"] = _preserve_document_root(
        ET.tostring(document_root, encoding="utf-8", xml_declaration=True),
        original_document_xml,
    )
    payloads["word/_rels/document.xml.rels"] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)
    payloads["[Content_Types].xml"] = ET.tostring(content_types_root, encoding="utf-8", xml_declaration=True)
    payloads["word/comments.xml"] = ET.tostring(comments_root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(destination_docx, "w") as archive:
        for filename, data in payloads.items():
            info = infos.get(filename)
            if info is not None:
                archive.writestr(info, data)
            else:
                archive.writestr(filename, data)

    return summary


def resolve_source_docx(contract: dict[str, Any], *, fallback_dir: Path | None = None) -> Path:
    """Resolve the usable source docx for a contract, synthesizing one for PDF when needed."""

    source_files = contract.get("source_files") or {}
    original_doc = Path(str(source_files.get("original_doc", "")))
    original_md = Path(str(source_files.get("original_md", "")))
    if original_doc.suffix.lower() == ".docx":
        return original_doc

    if original_md.exists():
        meta_path = original_md.with_name("meta.json")
        if meta_path.exists():
            meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
            conversion = meta_payload.get("doc_conversion") or {}
            output_path = conversion.get("output_path")
            if output_path:
                converted_docx = Path(str(output_path))
                if converted_docx.exists():
                    return converted_docx

    if original_doc.suffix.lower() == ".pdf":
        if fallback_dir is None:
            raise FileNotFoundError("PDF 输入需要提供 `fallback_dir` 以生成可批注的 docx。")
        safe_name = (str(contract.get("contract_id", "")).strip() or original_doc.stem or "contract").replace("/", "_")
        safe_name = safe_name.replace("\\", "_").replace(":", "_")
        synthesized_docx = fallback_dir / f"{safe_name}_pdf结构化审查底稿.docx"
        should_rebuild = not _is_valid_synthesized_docx(synthesized_docx)
        if synthesized_docx.exists() and original_md.exists():
            should_rebuild = should_rebuild or synthesized_docx.stat().st_mtime < original_md.stat().st_mtime
        if should_rebuild:
            build_docx_from_markdown(original_md, synthesized_docx, title=f"PDF结构化审查底稿：{original_doc.name}")
        return synthesized_docx

    meta_path = original_md.with_name("meta.json")
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json for doc conversion lookup: {meta_path}")

    meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
    conversion = meta_payload.get("doc_conversion") or {}
    output_path = conversion.get("output_path")
    if not output_path:
        raise FileNotFoundError(f"Missing converted docx path in meta.json: {meta_path}")
    return Path(str(output_path))


def resolve_meta_path(contract: dict[str, Any]) -> Path:
    source_files = contract.get("source_files") or {}
    original_md = Path(str(source_files.get("original_md", "")))
    return original_md.with_name("meta.json")


def _load_contracts_with_local_risks(result_path: Path) -> list[dict[str, Any]]:
    """Load contracts from either legacy dataset output or pure local result output."""

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    contracts = payload.get("contracts", [])
    if not isinstance(contracts, list):
        msg = f"`contracts` must be a list: {result_path}"
        raise ValueError(msg)

    normalized_contracts: list[dict[str, Any]] = []
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        normalized = dict(contract)
        local_risks = contract.get("local_llm_risks")
        if local_risks is None:
            local_risks = list((contract.get("participants") or {}).get("local_llm") or [])
        normalized["local_llm_risks"] = list(local_risks or [])
        normalized_contracts.append(normalized)
    return normalized_contracts


def export_local_llm_comment_docs(result_path: Path, output_dir: Path) -> dict[str, Any]:
    """Generate original-contract comment docs from local LLM JSON output."""

    output_dir.mkdir(parents=True, exist_ok=True)
    source_cache_dir = output_dir / "_source_docx_cache"

    contracts_summary: list[dict[str, Any]] = []
    markdown_lines = ["# 本地模型原合同批注导出", ""]

    for contract in _load_contracts_with_local_risks(result_path):
        contract_id = str(contract.get("contract_id", "")).strip()
        if not contract_id:
            continue

        source_files = contract.get("source_files") or {}
        original_doc = Path(str(source_files.get("original_doc", "")))
        source_docx = resolve_source_docx(contract, fallback_dir=source_cache_dir)
        meta_path = resolve_meta_path(contract)
        safe_name = contract_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        output_docx = output_dir / f"{safe_name}_本地模型批注版.docx"
        local_risks = list(contract.get("local_llm_risks") or [])
        comment_summary = annotate_docx_with_comments(
            source_docx,
            output_docx,
            local_risks,
            contract=contract,
            meta_path=meta_path,
        )

        source_mode = "generated_from_pdf" if original_doc.suffix.lower() == ".pdf" else "original_or_converted_docx"
        contract_summary = {
            "contract_id": contract_id,
            "original_input": str(original_doc),
            "source_docx": str(source_docx),
            "source_mode": source_mode,
            "source_display_name": original_doc.stem or source_docx.stem,
            "output_docx": str(output_docx),
            "risk_count": len(local_risks),
            "comment_count": len(comment_summary),
            "comments": comment_summary,
        }
        contracts_summary.append(contract_summary)

        markdown_lines.extend(
            [
                f"## {contract_id}",
                "",
                f"- 原始输入: `{original_doc}`",
                f"- 批注底稿: `{source_docx}`",
                f"- 底稿类型: `{source_mode}`",
                f"- 批注文档: `{output_docx}`",
                f"- 风险点数量: `{len(local_risks)}`",
                "",
            ]
        )
        for item in comment_summary:
            markdown_lines.extend(
                [
                    f"### {item['title']}",
                    "",
                    f"- 风险ID: `{item['risk_id']}`",
                    f"- 锚定策略: `{item['anchor_strategy']}`",
                    f"- 段落范围: `{item['start_paragraph_index']} - {item['end_paragraph_index']}`",
                    f"- 命中文本: `{item['matched_text']}`",
                    "",
                ]
            )

    summary_payload = {
        "result_path": str(result_path),
        "generated_at": datetime.now().isoformat(),
        "output_dir": str(output_dir),
        "contracts": contracts_summary,
    }

    (output_dir / "批注导出结果.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "批注导出结果.md").write_text("\n".join(markdown_lines), encoding="utf-8")
    return summary_payload
