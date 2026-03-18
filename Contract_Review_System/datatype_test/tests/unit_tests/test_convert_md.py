from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "convert_md.py"
SPEC = importlib.util.spec_from_file_location("datatype_test_convert_md", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
convert_md = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = convert_md
SPEC.loader.exec_module(convert_md)


def _write_docx(path: Path, document_xml: str, comments_xml: str | None = None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>
""".encode("utf-8"),
        )
        archive.writestr("word/document.xml", document_xml.encode("utf-8"))
        if comments_xml is not None:
            archive.writestr("word/comments.xml", comments_xml.encode("utf-8"))


def test_prepare_docx_for_docling_flattens_alternate_content(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    _write_docx(
        source,
        """<?xml version="1.0" encoding="UTF-8"?>
<w:document
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
  <w:body>
    <w:p>
      <w:r>
        <mc:AlternateContent>
          <mc:Choice Requires="wps">
            <w:drawing />
          </mc:Choice>
          <mc:Fallback>
            <w:pict />
          </mc:Fallback>
        </mc:AlternateContent>
      </w:r>
    </w:p>
  </w:body>
</w:document>
""",
    )

    sanitized_path, info = convert_md.prepare_docx_for_docling(source, tmp_path / "prepared")

    assert info is not None
    assert info["applied"] is True
    assert info["alternate_content_count"] == 1
    assert sanitized_path.exists()

    with zipfile.ZipFile(sanitized_path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "AlternateContent" not in document_xml
    document_root = ET.fromstring(document_xml)
    assert any(node.tag.endswith("pict") for node in document_root.iter())


def test_reuse_mislabeled_docx_package(tmp_path: Path) -> None:
    source = tmp_path / "mislabeled.doc"
    _write_docx(
        source,
        """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>hello</w:t></w:r></w:p>
  </w:body>
</w:document>
""",
    )

    reused = convert_md.reuse_mislabeled_docx_package(source, tmp_path / "converted")

    assert reused is not None
    assert reused.suffix == ".docx"
    assert reused.exists()
    assert convert_md.detect_word_file_format(source) == "docx_package"


def test_reuse_previous_converted_docx_prefers_latest_prior_run(tmp_path: Path) -> None:
    source = tmp_path / "source.doc"
    source.write_bytes(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1dummy-doc")

    output_root = tmp_path / "outputs_md"
    output_subdir = Path("3-保密协议") / "1-原合同-保密协议"

    older_docx = output_root / "20260316_full_eval" / output_subdir / "_converted" / "source.docx"
    older_docx.parent.mkdir(parents=True, exist_ok=True)
    _write_docx(
        older_docx,
        """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>older</w:t></w:r></w:p>
  </w:body>
</w:document>
""",
    )

    newer_docx = output_root / "20260317_full_eval_fixscan" / output_subdir / "_converted" / "source.docx"
    newer_docx.parent.mkdir(parents=True, exist_ok=True)
    _write_docx(
        newer_docx,
        """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>newer</w:t></w:r></w:p>
  </w:body>
</w:document>
""",
    )

    reused, method = convert_md.reuse_previous_converted_docx(
        source,
        tmp_path / "converted",
        output_root,
        output_subdir,
        current_run_id="20260317_full_eval_fixscan_v3",
    )

    assert reused is not None
    assert reused.exists()
    assert method == "previous_run_cache:20260317_full_eval_fixscan"

    with zipfile.ZipFile(reused) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "newer" in document_xml


def test_table_comment_uses_row_context_for_markdown_injection(tmp_path: Path) -> None:
    source = tmp_path / "table_comments.docx"
    _write_docx(
        source,
        """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl>
      <w:tr>
        <w:tc>
          <w:p><w:r><w:t>付款期限为5日</w:t></w:r></w:p>
        </w:tc>
        <w:tc>
          <w:p>
            <w:commentRangeStart w:id="0" />
            <w:r><w:t>修改建议</w:t></w:r>
            <w:commentRangeEnd w:id="0" />
            <w:r><w:commentReference w:id="0" /></w:r>
          </w:p>
        </w:tc>
        <w:tc>
          <w:p><w:r><w:t>将付款期限改为10日</w:t></w:r></w:p>
        </w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>
""",
        """<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="审核人">
    <w:p><w:r><w:t>这里要和原文保持一致</w:t></w:r></w:p>
  </w:comment>
</w:comments>
""",
    )

    anchors = convert_md.extract_docx_comments_with_anchors(source)
    assert len(anchors) == 1
    assert anchors[0]["paragraph_excerpt"] == "修改建议"
    assert any("付款期限为5日" in candidate for candidate in anchors[0]["match_candidates"])

    markdown = "\n".join(
        [
            "| 条款原文 | 修改建议 | 说明 |",
            "| --- | --- | --- |",
            "| 付款期限为5日 | 修改建议 | 将付款期限改为10日 |",
        ]
    )
    enriched, stats = convert_md.inject_inline_annotations(markdown, anchors, [])

    assert stats["comment_matched"] == 1
    assert stats["comment_unmatched"] == 0
    assert "批注#0" in enriched
    assert "这里要和原文保持一致" in enriched


def test_numbered_comment_prefers_same_clause_line_over_longer_context_candidate() -> None:
    markdown = "\n".join(
        [
            "**5. 违约责任**",
            "",
            "5.1因乙方违反本协议给甲方造成损失的，应赔偿甲方因此所遭受的直接经济损失。",
            "",
            "5．2本协议，乙方从甲方取得的与该项目相关资料应返还给甲方。",
        ]
    )
    anchors = [
        {
            "comment_id": "13",
            "author": "Mia",
            "comment_text": "这条批注应该挂到5.2。",
            "paragraph_index": 46,
            "paragraph_excerpt": "5．2无论何种原因致使甲、乙双方不能继续执行本协议，乙方应返还全部资料。",
            "match_candidates": [
                "5.1因乙方违反本协议给甲方造成损失的，应赔偿甲方因此所遭受的直接经济损失。5．2无论何种原因致使甲、乙双方不能继续执行本协议，乙方应返还全部资料。",
                "5．2无论何种原因致使甲、乙双方不能继续执行本协议，乙方应返还全部资料。",
            ],
        }
    ]

    enriched, stats = convert_md.inject_inline_annotations(markdown, anchors, [])

    assert stats["comment_matched"] == 1
    assert stats["comment_unmatched"] == 0
    assert "批注#13" not in enriched.splitlines()[2]
    assert "批注#13" in enriched.splitlines()[4]


def test_repair_missing_numbered_paragraphs_inserts_dropped_source_lines() -> None:
    markdown = "\n".join(
        [
            "**一、服务范围**",
            "",
            "1、服务项目：宇通客车坦桑尼亚253台车播放器软件升级",
            "2、服务产品：HPH07播放器",
            "3、服务地点：坦桑尼亚",
            "4、服务完成时间：至 2026年03月31日前",
            "5、",
            "",
            "服务内容简述：",
            "",
            ".1  服务期内，乙方安排人员在坦桑尼亚国家对甲方在宇通客车上装配的253台播放器产品进行软件升级。",
        ]
    )
    source_paragraphs = [
        "一、服务范围",
        "1、服务项目：宇通客车坦桑尼亚253台车播放器软件升级",
        "2、服务产品：HPH07播放器",
        "3、服务地点：坦桑尼亚",
        "4、服务完成时间：至 2026年03月31日前",
        "5、服务资质：乙方承诺具备提供本协议约定服务的相关资质，并提供相应的资质证明文件作为合同附件。",
        "6、服务内容简述：",
        "6.1  服务期内，乙方安排人员在坦桑尼亚国家对甲方在宇通客车上装配的253台播放器产品进行软件升级。",
        "6.2服务标准：升级后的设备需通过甲方指定的功能程序。",
        "6.3验收：乙方应于服务完成后3个工作日内提交书面验收申请。",
    ]

    repaired, stats = convert_md.repair_missing_numbered_paragraphs(markdown, source_paragraphs)

    assert stats["inserted_count"] >= 3
    assert "5、服务资质：" in repaired
    assert "6、服务内容简述：" in repaired
    assert "6.2服务标准：" in repaired
    assert "6.3验收：" in repaired
