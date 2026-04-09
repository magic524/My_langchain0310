from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .runtime_types import ClauseRisk, ContractBackgroundBrief, ContractReviewResult


def _xml_run(text: str, *, bold: bool = False) -> str:
    escaped = escape(text)
    run_properties = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{run_properties}<w:t xml:space="preserve">{escaped}</w:t></w:r>'


def _xml_paragraph(text: str, *, style: str | None = None, bold: bool = False) -> str:
    paragraph_properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{paragraph_properties}{_xml_run(text, bold=bold)}</w:p>'


def _xml_cell_paragraphs(lines: list[str], *, bold_first: bool = False) -> str:
    paragraphs: list[str] = []
    for index, line in enumerate(lines):
        paragraphs.append(_xml_paragraph(line, bold=bold_first and index == 0))
    return "".join(paragraphs) or _xml_paragraph("")


def _xml_table_two_columns(rows: list[tuple[list[str], list[str]]]) -> str:
    row_xml: list[str] = []
    for left_lines, right_lines in rows:
        row_xml.append(
            "".join(
                [
                    "<w:tr>",
                    '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>',
                    _xml_cell_paragraphs(left_lines),
                    "</w:tc>",
                    '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>',
                    _xml_cell_paragraphs(right_lines),
                    "</w:tc>",
                    "</w:tr>",
                ]
            )
        )
    return (
        "<w:tbl>"
        "<w:tblPr>"
        '<w:tblStyle w:val="TableGrid"/>'
        '<w:tblW w:w="9000" w:type="dxa"/>'
        "</w:tblPr>"
        '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
        + "".join(row_xml)
        + "</w:tbl>"
    )


def _xml_table_merged_row(text: str) -> str:
    return "".join(
        [
            "<w:tr>",
            '<w:tc><w:tcPr><w:gridSpan w:val="2"/><w:tcW w:w="9000" w:type="dxa"/></w:tcPr>',
            _xml_cell_paragraphs([text]),
            "</w:tc>",
            "</w:tr>",
        ]
    )


def _xml_risk_detail_table(original_text: str, suggested_text: str, reason_text: str) -> str:
    return (
        "<w:tbl>"
        "<w:tblPr>"
        '<w:tblStyle w:val="TableGrid"/>'
        '<w:tblW w:w="9000" w:type="dxa"/>'
        "</w:tblPr>"
        '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
        + "".join(
            [
                '<w:tr>'
                '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
                + _xml_cell_paragraphs(["条款原文"], bold_first=True)
                + '</w:tc>'
                '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
                + _xml_cell_paragraphs(["修改建议"], bold_first=True)
                + '</w:tc>'
                '</w:tr>',
                '<w:tr>'
                '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
                + _xml_cell_paragraphs((original_text or "无").splitlines() or ["无"])
                + '</w:tc>'
                '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
                + _xml_cell_paragraphs((suggested_text or "无").splitlines() or ["无"])
                + '</w:tc>'
                '</w:tr>',
                _xml_table_merged_row("修改理由"),
                _xml_table_merged_row(reason_text or "无"),
            ]
        )
        + "</w:tbl>"
    )


def _build_background_lines(brief: ContractBackgroundBrief) -> list[str]:
    lines = [
        f"合同类型：{brief.contract_type or '未识别'}",
        f"交易目标：{brief.transaction_purpose or '未识别'}",
        f"角色关系：{brief.parties_summary or '未识别'}",
    ]
    if brief.performance_path:
        lines.append("关键履约主线：")
        lines.extend([f"- {item}" for item in brief.performance_path])
    if brief.high_risk_topics:
        lines.append("高风险主题：")
        lines.extend([f"- {item}" for item in brief.high_risk_topics])
    if brief.review_focus:
        lines.append("统一关注点：")
        lines.extend([f"- {item}" for item in brief.review_focus])
    return lines


def build_report_payload(contract_result: ContractReviewResult) -> dict[str, Any]:
    """Build a report-oriented JSON payload from the structured review result."""

    risk_items: list[dict[str, Any]] = []
    for index, risk in enumerate(contract_result.aggregated_risks, start=1):
        risk_items.append(
            {
                "index": index,
                "title": risk.risk_title or f"风险点{index}",
                "risk_level": risk.risk_level,
                "risk_type": risk.risk_type,
                "parent_clause_id": risk.parent_clause_id,
                "target_clause_id": risk.target_clause_id,
                "original_clause_text": risk.target_text or risk.evidence_source or "",
                "suggested_revision": risk.suggestion or "无",
                "reason_text": risk.explanation or "无",
                "evidence_source": risk.evidence_source,
            }
        )

    return {
        "contract_id": contract_result.contract_id,
        "background_brief": asdict(contract_result.background_brief),
        "risk_statistics": contract_result.risk_statistics,
        "risk_items": risk_items,
    }


def build_docx_from_report_payload(report_payload: dict[str, Any], destination_docx: Path) -> Path:
    """Render a structured report payload into a Word document."""

    title = f"关于《{report_payload['contract_id']}》的审查意见书"
    brief = ContractBackgroundBrief(**report_payload.get("background_brief", {}))
    stats = report_payload.get("risk_statistics", {})
    risk_items = report_payload.get("risk_items", [])

    blocks: list[str] = [
        _xml_paragraph(title, style="Heading1"),
        _xml_paragraph("一、合同背景摘要", style="Heading2"),
    ]
    blocks.extend(_xml_paragraph(line) for line in _build_background_lines(brief))

    blocks.append(_xml_paragraph("二、风险点统计", style="Heading2"))
    statistic_rows: list[tuple[list[str], list[str]]] = [(["维度"], ["数量"]), (["风险总数"], [str(stats.get("risk_count", 0))])]
    for level, count in stats.get("by_level", {}).items():
        statistic_rows.append(([f"等级：{level}"], [str(count)]))
    for risk_type, count in stats.get("by_type", {}).items():
        statistic_rows.append(([f"类型：{risk_type}"], [str(count)]))
    blocks.append(_xml_table_two_columns(statistic_rows))

    blocks.append(_xml_paragraph("三、详细审查意见", style="Heading2"))
    if not risk_items:
        blocks.append(_xml_paragraph("本次未识别到结构化风险点。"))
    else:
        for risk in risk_items:
            blocks.append(_xml_paragraph(f"{risk['index']}. {risk['title']}", style="Heading3"))
            blocks.append(
                _xml_risk_detail_table(
                    risk.get("original_clause_text", "") or "无",
                    risk.get("suggested_revision", "") or "无",
                    risk.get("reason_text", "") or "无",
                )
            )

    document_xml = "".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
            "<w:body>",
            *blocks,
            (
                '<w:sectPr>'
                '<w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
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
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    document_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults>'
        '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="宋体"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr/></w:pPrDefault>'
        '</w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        '</w:styles>'
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Microsoft Office Word</Application>'
        '</Properties>'
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<dc:title>{escape(title)}</dc:title>'
        '<dc:creator>Contract Review System</dc:creator>'
        '<cp:lastModifiedBy>Contract Review System</cp:lastModifiedBy>'
        '</cp:coreProperties>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '</Types>'
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


def _write_background_brief_files(brief: ContractBackgroundBrief, output_dir: Path) -> tuple[Path, Path]:
    brief_json_path = output_dir / "contract_background_brief.json"
    brief_text_path = output_dir / "合同背景摘要.txt"
    brief_json_path.write_text(json.dumps(asdict(brief), ensure_ascii=False, indent=2), encoding="utf-8")
    brief_text_path.write_text("\n".join(_build_background_lines(brief)), encoding="utf-8")
    return brief_json_path, brief_text_path


def export_contract_report(contract_result: ContractReviewResult, output_dir: Path) -> dict[str, str]:
    """Export report docx/json artifacts directly from structured CRSv1 data."""

    output_dir.mkdir(parents=True, exist_ok=True)
    report_docx_path = output_dir / "审查报告.docx"
    report_payload_path = output_dir / "report_payload.json"
    stats_path = output_dir / "risk_statistics.json"

    report_payload = build_report_payload(contract_result)
    report_payload_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    build_docx_from_report_payload(report_payload, report_docx_path)
    brief_json_path, brief_text_path = _write_background_brief_files(contract_result.background_brief, output_dir)
    stats_path.write_text(
        json.dumps(
            {
                "contract_id": contract_result.contract_id,
                "risk_statistics": contract_result.risk_statistics,
                "aggregated_risks": [asdict(risk) for risk in contract_result.aggregated_risks],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "report_docx_path": str(report_docx_path),
        "report_payload_path": str(report_payload_path),
        "statistics_path": str(stats_path),
        "background_brief_json_path": str(brief_json_path),
        "background_brief_text_path": str(brief_text_path),
    }
