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

from .runtime_types import ClauseRisk, ContractReviewResult
from .text_utils import normalize_text, safe_filename, text_similarity


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
NS = {"w": WORD_NS, "r": REL_NS}
DOCUMENT_ROOT_RE = re.compile(r"<w:document\b[^>]*>", re.IGNORECASE)
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
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "cx1": "http://schemas.microsoft.com/office/drawing/2015/9/8/chartex",
    "cx2": "http://schemas.microsoft.com/office/drawing/2015/10/21/chartex",
    "cx3": "http://schemas.microsoft.com/office/drawing/2016/5/9/chartex",
    "cx4": "http://schemas.microsoft.com/office/drawing/2016/5/10/chartex",
    "cx5": "http://schemas.microsoft.com/office/drawing/2016/5/11/chartex",
    "cx6": "http://schemas.microsoft.com/office/drawing/2016/5/12/chartex",
    "cx7": "http://schemas.microsoft.com/office/drawing/2016/5/13/chartex",
    "cx8": "http://schemas.microsoft.com/office/drawing/2016/5/14/chartex",
    "aink": "http://schemas.microsoft.com/office/drawing/2016/ink",
    "am3d": "http://schemas.microsoft.com/office/drawing/2017/model3d",
}

ET.register_namespace("w", WORD_NS)
ET.register_namespace("r", REL_NS)
for prefix, uri in DOCX_PREFIXES.items():
    ET.register_namespace(prefix, uri)


def _w_tag(local_name: str) -> str:
    return f"{{{WORD_NS}}}{local_name}"


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
    score: float


def paragraph_text(paragraph: ET.Element) -> str:
    """Return visible paragraph text from a Word paragraph."""

    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == _w_tag("t") and node.text:
            parts.append(node.text)
        elif node.tag in {_w_tag("tab"), _w_tag("br"), _w_tag("cr")}:
            parts.append(" ")
    return "".join(parts).strip()


def _dedupe_nonempty(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_text(value)
        if not normalized or normalized in seen:
            continue
        deduped.append(value.strip())
        seen.add(normalized)
    return deduped


def extract_paragraphs(document_root: ET.Element) -> list[ParagraphRecord]:
    """Extract visible paragraphs and lightweight context candidates."""

    paragraph_elements = document_root.findall(".//w:p", NS)
    visible_texts = [paragraph_text(item) for item in paragraph_elements]
    records: list[ParagraphRecord] = []
    for position, paragraph in enumerate(paragraph_elements):
        text = visible_texts[position]
        if not text.strip():
            continue
        candidates = [text]
        if position > 0 and visible_texts[position - 1].strip():
            candidates.append(visible_texts[position - 1])
            candidates.append(f"{visible_texts[position - 1]} {text}")
        if position + 1 < len(visible_texts) and visible_texts[position + 1].strip():
            candidates.append(visible_texts[position + 1])
            candidates.append(f"{text} {visible_texts[position + 1]}")
        records.append(
            ParagraphRecord(
                index=len(records) + 1,
                text=text,
                normalized_text=normalize_text(text),
                element=paragraph,
                match_candidates=_dedupe_nonempty(candidates),
            )
        )
    return records


def _score_candidate(candidate: str, target: str) -> float:
    candidate_norm = normalize_text(candidate)
    target_norm = normalize_text(target)
    if not candidate_norm or not target_norm:
        return 0.0
    if target_norm in candidate_norm:
        return 10.0 + len(target_norm) / 100.0
    return text_similarity(candidate_norm, target_norm)


def find_best_anchor(paragraphs: list[ParagraphRecord], risk: ClauseRisk) -> AnchorMatch:
    """Find the best paragraph anchor for one risk item."""

    if not paragraphs:
        raise ValueError("No paragraphs available for anchoring")

    search_texts = _dedupe_nonempty(
        [
            risk.target_text,
            risk.evidence_source,
            risk.risk_title,
            risk.explanation,
        ]
    )
    if not search_texts:
        paragraph = paragraphs[0]
        return AnchorMatch(
            start_index=paragraph.index,
            end_index=paragraph.index,
            matched_text=paragraph.text,
            strategy="first_paragraph_fallback",
            score=0.0,
        )

    best_match: AnchorMatch | None = None
    for paragraph in paragraphs:
        best_score = 0.0
        best_strategy = "similarity"
        for search_text in search_texts:
            direct_score = _score_candidate(paragraph.text, search_text)
            if normalize_text(search_text) and normalize_text(search_text) in paragraph.normalized_text:
                direct_score += 8.0
                best_strategy = "direct_paragraph_match"
            elif direct_score > 0:
                direct_score += 1.5
            if direct_score > best_score:
                best_score = direct_score
        for candidate in paragraph.match_candidates:
            if candidate == paragraph.text:
                continue
            for search_text in search_texts:
                score = _score_candidate(candidate, search_text)
                if normalize_text(search_text) and normalize_text(search_text) in normalize_text(candidate):
                    score += 3.0
                    best_strategy = "context_text_match"
                if score > best_score:
                    best_score = score
        if best_score <= 0:
            continue
        candidate_match = AnchorMatch(
            start_index=paragraph.index,
            end_index=paragraph.index,
            matched_text=paragraph.text,
            strategy=best_strategy,
            score=best_score,
        )
        if best_match is None or candidate_match.score > best_match.score:
            best_match = candidate_match

    if best_match is not None:
        return best_match

    paragraph = max(paragraphs, key=lambda item: len(item.normalized_text))
    return AnchorMatch(
        start_index=paragraph.index,
        end_index=paragraph.index,
        matched_text=paragraph.text,
        strategy="longest_paragraph_fallback",
        score=0.0,
    )


def _preserve_document_root(serialized_xml: bytes, original_xml: bytes) -> bytes:
    """Preserve the original document root declarations for compatibility."""

    serialized_text = serialized_xml.decode("utf-8")
    original_text = original_xml.decode("utf-8")
    serialized_match = DOCUMENT_ROOT_RE.search(serialized_text)
    original_match = DOCUMENT_ROOT_RE.search(original_text)
    if serialized_match is None or original_match is None:
        return serialized_xml
    return f"{original_text[:original_match.end()]}{serialized_text[serialized_match.end():]}".encode("utf-8")


def _ensure_comments_tree(zip_entries: dict[str, bytes]) -> ET.Element:
    raw_comments = zip_entries.get("word/comments.xml")
    if raw_comments is not None:
        return ET.fromstring(raw_comments)
    return ET.fromstring(f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments xmlns:w="{WORD_NS}"/>')


def _ensure_document_relationship_tree(rels_root: ET.Element) -> None:
    existing = rels_root.findall(_pkg_rel_tag("Relationship"))
    for rel in existing:
        if rel.attrib.get("Type") == COMMENTS_REL_TYPE:
            return
    used_ids = {rel.attrib.get("Id", "") for rel in existing}
    index = 1
    while f"rId{index}" in used_ids:
        index += 1
    rels_root.append(
        ET.Element(
            _pkg_rel_tag("Relationship"),
            {"Id": f"rId{index}", "Type": COMMENTS_REL_TYPE, "Target": "comments.xml"},
        )
    )


def _ensure_content_type_tree(root: ET.Element) -> None:
    for override in root.findall(_content_type_tag("Override")):
        if override.attrib.get("PartName") == "/word/comments.xml":
            return
    root.append(
        ET.Element(
            _content_type_tag("Override"),
            {"PartName": "/word/comments.xml", "ContentType": COMMENTS_CONTENT_TYPE},
        )
    )


def _next_comment_id(comments_root: ET.Element) -> int:
    ids: list[int] = []
    for comment in comments_root.findall(_w_tag("comment")):
        raw_value = comment.attrib.get(_w_tag("id")) or comment.attrib.get("id")
        if raw_value is None:
            continue
        try:
            ids.append(int(raw_value))
        except ValueError:
            continue
    return max(ids, default=-1) + 1


def _comment_reference_run(comment_id: int) -> ET.Element:
    run = ET.Element(_w_tag("r"))
    run_properties = ET.SubElement(run, _w_tag("rPr"))
    ET.SubElement(run_properties, _w_tag("rStyle"), {_w_tag("val"): "CommentReference"})
    ET.SubElement(run, _w_tag("commentReference"), {_w_tag("id"): str(comment_id)})
    return run


def _make_comment_body(risk: ClauseRisk) -> str:
    """Format comment body to match the reviewed style."""

    level_label = {
        "missing": "信息缺失风险",
        "high": "高风险",
        "low": "低风险",
    }.get(risk.risk_level, risk.risk_level or "未标注")
    lines = [f"风险点：{risk.risk_title or '未命名风险'}"]
    lines.append(f"风险级别：{level_label}")
    if risk.explanation:
        lines.append(f"说明：{risk.explanation}")
    if risk.suggestion:
        lines.append(f"建议：{risk.suggestion}")
    location_text = risk.target_text or risk.evidence_source
    if location_text:
        lines.append(f"定位：{location_text}")
    return "\n".join(lines)


def _comment_element(comment_id: int, body: str, author: str) -> ET.Element:
    comment = ET.Element(
        _w_tag("comment"),
        {
            _w_tag("id"): str(comment_id),
            _w_tag("author"): author,
            _w_tag("initials"): "CRS",
            _w_tag("date"): datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
    )
    for line in body.splitlines():
        paragraph = ET.SubElement(comment, _w_tag("p"))
        run = ET.SubElement(paragraph, _w_tag("r"))
        text = ET.SubElement(run, _w_tag("t"))
        text.text = line
    return comment


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


def resolve_source_docx(contract_result: ContractReviewResult) -> Path:
    """Resolve the actual source docx for annotation."""

    source_files = contract_result.source_files
    original_doc = Path(str(source_files.get("original_doc", "")))
    if original_doc.exists() and original_doc.suffix.lower() == ".docx":
        return original_doc

    meta_path = Path(str(source_files.get("meta_path", "")))
    if meta_path.exists():
        meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
        doc_conversion = meta_payload.get("doc_conversion") or {}
        converted = Path(str(doc_conversion.get("output_path", "")))
        if converted.exists() and converted.suffix.lower() == ".docx":
            return converted

    msg = f"Could not resolve source docx for contract: {contract_result.contract_id}"
    raise FileNotFoundError(msg)


def annotate_docx_with_comments(source_docx: Path, output_docx: Path, risks: list[ClauseRisk]) -> list[dict[str, Any]]:
    """Copy a docx and inject Word comments for CRSv1 risks."""

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    if not risks:
        shutil.copy2(source_docx, output_docx)
        return []

    shutil.copy2(source_docx, output_docx)
    with zipfile.ZipFile(output_docx, "r") as archive:
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
    comments_root = _ensure_comments_tree(payloads)

    _ensure_document_relationship_tree(rels_root)
    _ensure_content_type_tree(content_types_root)

    paragraphs = extract_paragraphs(document_root)
    if not paragraphs:
        raise RuntimeError(f"No visible paragraphs found in docx: {source_docx}")
    paragraphs_by_index = {item.index: item for item in paragraphs}
    next_comment_id = _next_comment_id(comments_root)

    summary: list[dict[str, Any]] = []
    for risk in risks:
        match = find_best_anchor(paragraphs, risk)
        comment_id = next_comment_id
        next_comment_id += 1

        _insert_range_markers(paragraphs_by_index, match, comment_id)
        comments_root.append(_comment_element(comment_id, _make_comment_body(risk), "CRSv1"))
        summary.append(
            {
                "risk_id": risk.risk_id,
                "title": risk.risk_title,
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
    payloads["word/comments.xml"] = ET.tostring(comments_root, encoding="utf-8", xml_declaration=True)
    payloads["word/_rels/document.xml.rels"] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)
    payloads["[Content_Types].xml"] = ET.tostring(content_types_root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(output_docx, "w") as archive:
        for filename, data in payloads.items():
            info = infos.get(filename)
            if info is not None:
                archive.writestr(info, data)
            else:
                archive.writestr(filename, data)
    return summary


def export_contract_comment_doc(contract_result: ContractReviewResult, output_dir: Path) -> dict[str, Any]:
    """Export one annotated docx file for a contract result."""

    source_docx = resolve_source_docx(contract_result)
    output_docx = output_dir / f"{safe_filename(contract_result.contract_id)}_CRSv1批注版.docx"
    selected_risks = contract_result.report_summary.get("selected_risks")
    risks = selected_risks if isinstance(selected_risks, list) else contract_result.aggregated_risks
    comment_summary = annotate_docx_with_comments(source_docx, output_docx, risks)
    return {
        "contract_id": contract_result.contract_id,
        "source_docx": str(source_docx),
        "output_docx": str(output_docx),
        "risk_count": len(risks),
        "comment_count": len(comment_summary),
        "comments": comment_summary,
    }
