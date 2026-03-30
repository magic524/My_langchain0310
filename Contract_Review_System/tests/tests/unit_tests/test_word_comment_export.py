from __future__ import annotations

import json
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from only_prompt_local_llm.word_comment_export import (
    annotate_docx_with_comments,
    find_best_anchor,
    normalize_text,
    resolve_source_docx,
)


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _build_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    document_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
        "<w:body>",
    ]
    for paragraph in paragraphs:
        document_lines.append(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>")
    document_lines.extend(["<w:sectPr/>", "</w:body>", "</w:document>"])
    document_xml = "".join(document_lines)

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", rels_xml)


def _build_namespaced_docx(path: Path, paragraphs: list[str]) -> None:
    document_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        (
            '<w:document '
            'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
            'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
            'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
            'mc:Ignorable="w14 w15 wp14">'
        ),
        "<w:body>",
    ]
    for paragraph in paragraphs:
        document_lines.append(f"<w:p w14:paraId=\"12345678\"><w:r><w:t>{paragraph}</w:t></w:r></w:p>")
    document_lines.extend(["<w:sectPr/>", "</w:body>", "</w:document>"])
    document_xml = "".join(document_lines)

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", rels_xml)


def test_find_best_anchor_matches_multi_paragraph_clause() -> None:
    paragraphs = [
        type(
            "P",
            (),
            {
                "index": 1,
                "text": "甲方：",
                "normalized_text": normalize_text("甲方："),
                "element": ET.Element("p"),
                "match_candidates": [normalize_text("甲方："), normalize_text("甲方： 法定代表人：")],
            },
        )(),
        type(
            "P",
            (),
            {
                "index": 2,
                "text": "法定代表人：",
                "normalized_text": normalize_text("法定代表人："),
                "element": ET.Element("p"),
                "match_candidates": [normalize_text("法定代表人："), normalize_text("甲方： 法定代表人： 地址：")],
            },
        )(),
        type(
            "P",
            (),
            {
                "index": 3,
                "text": "地址：",
                "normalized_text": normalize_text("地址："),
                "element": ET.Element("p"),
                "match_candidates": [normalize_text("地址："), normalize_text("法定代表人： 地址：")],
            },
        )(),
        type(
            "P",
            (),
            {
                "index": 4,
                "text": "其他条款",
                "normalized_text": normalize_text("其他条款"),
                "element": ET.Element("p"),
                "match_candidates": [normalize_text("其他条款")],
            },
        )(),
    ]

    match = find_best_anchor(paragraphs, "甲方：\n\n法定代表人：\n\n地址：")

    assert match.start_index == 2
    assert match.end_index == 2
    assert match.strategy in {"context_or_table_match", "direct_clause_match"}


def test_find_best_anchor_falls_back_for_missing_clause() -> None:
    paragraphs = [
        type(
            "P",
            (),
            {
                "index": 1,
                "text": "合同标题",
                "normalized_text": normalize_text("合同标题"),
                "element": ET.Element("p"),
                "match_candidates": [normalize_text("合同标题")],
            },
        )()
    ]

    match = find_best_anchor(paragraphs, "（全文未涉及不可抗力条款）")

    assert match.start_index == 1
    assert match.end_index == 1
    assert match.strategy == "document_fallback"


def test_annotate_docx_with_comments_creates_comments_part(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    destination = tmp_path / "annotated.docx"
    _build_minimal_docx(source, ["争议解决条款", "违约责任条款"])

    summary = annotate_docx_with_comments(
        source,
        destination,
        [
            {
                "risk_id": "risk-1",
                "title": "争议解决管辖不利",
                "clause_text": "争议解决条款",
                "explanation": "说明文本",
                "suggestion": "建议文本",
            }
        ],
    )

    assert len(summary) == 1
    with zipfile.ZipFile(destination) as archive:
        assert "word/comments.xml" in archive.namelist()
        document_root = ET.fromstring(archive.read("word/document.xml"))
        comments_root = ET.fromstring(archive.read("word/comments.xml"))

    assert document_root.findall(".//w:commentRangeStart", WORD_NS)
    assert document_root.findall(".//w:commentRangeEnd", WORD_NS)
    comments = comments_root.findall(".//w:comment", WORD_NS)
    assert len(comments) == 1
    assert "风险点：争议解决管辖不利" in "".join(comments[0].itertext())


def test_annotate_docx_with_comments_preserves_document_root_namespaces(tmp_path: Path) -> None:
    source = tmp_path / "source_namespaced.docx"
    destination = tmp_path / "annotated_namespaced.docx"
    _build_namespaced_docx(source, ["争议解决条款"])

    annotate_docx_with_comments(
        source,
        destination,
        [
            {
                "risk_id": "risk-1",
                "title": "争议解决管辖不利",
                "clause_text": "争议解决条款",
                "explanation": "说明文本",
                "suggestion": "建议文本",
            }
        ],
    )

    with zipfile.ZipFile(destination) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"' in document_xml
    assert 'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"' in document_xml
    assert 'mc:Ignorable="w14 w15 wp14"' in document_xml


def test_resolve_source_docx_uses_cached_conversion(tmp_path: Path) -> None:
    run_dir = tmp_path / "run" / "contract-a"
    md_dir = run_dir / "1-原合同"
    md_dir.mkdir(parents=True)
    original_md = md_dir / "output.md"
    original_md.write_text("# demo", encoding="utf-8")

    converted = md_dir / "_converted" / "demo.docx"
    converted.parent.mkdir(parents=True)
    converted.write_bytes(b"PK\x03\x04demo")

    meta_payload = {
        "doc_conversion": {
            "success": True,
            "method": "win32com",
            "output_path": str(converted),
        }
    }
    (md_dir / "meta.json").write_text(json.dumps(meta_payload, ensure_ascii=False), encoding="utf-8")

    contract = {
        "source_files": {
            "original_doc": str(tmp_path / "source.doc"),
            "original_md": str(original_md),
        }
    }

    assert resolve_source_docx(contract) == converted
