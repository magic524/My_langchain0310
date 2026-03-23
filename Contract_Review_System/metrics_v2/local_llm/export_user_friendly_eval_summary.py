from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


SOURCE_DIR = Path(
    r"Contract_Review_System\metrics_v2\local_llm\outputs_fix2\20260317_word2md_eval_third_party_fix2_20260318\细节对比_fix"
)
SOURCE_MD = SOURCE_DIR / "20260317_word2md_eval_总体汇总.md"
OUTPUT_XLSX = SOURCE_DIR / "20260317_word2md_eval_通俗版风险点汇总.xlsx"

RISK_LINE_RE = re.compile(
    r"^\| (?P<contract>[^|]+?) \| (?P<party>本地模型|第三方平台) \| "
    r"(?P<scope>口径A（仅采纳 \+ 部分采纳）|口径B（全部标签）) \| "
    r"(?P<clause>[^|]+?) \| (?P<clause_f1>[^|]+?) \| "
    r"(?P<risk>\d+/\d+/\d+) \| (?P<risk_f1>[^|]+?) \|$"
)


def parse_triplet(value: str) -> tuple[int, int, int]:
    parts = value.strip().split("/")
    return int(parts[0]), int(parts[1]), int(parts[2])


def format_percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "-"
    return f"{numerator / denominator:.2%}"


def load_summary_rows() -> dict[str, list[dict[str, str | int]]]:
    text = SOURCE_MD.read_text(encoding="utf-8")
    result: dict[str, list[dict[str, str | int]]] = {
        "口径A（仅采纳 + 部分采纳）": [],
        "口径B（全部标签）": [],
    }

    for line in text.splitlines():
        match = RISK_LINE_RE.match(line.strip())
        if not match:
            continue

        contract = match.group("contract")
        party = match.group("party")
        scope = match.group("scope")
        hit_count, over_report_count, missed_count = parse_triplet(match.group("risk"))
        manual_count = hit_count + missed_count
        predicted_count = hit_count + over_report_count

        result[scope].append(
            {
                "合同": contract,
                "对象": party,
                "人工确认风险点数": manual_count,
                "识别风险点数": predicted_count,
                "预测正确数": hit_count,
                "多报数": over_report_count,
                "漏报数": missed_count,
                "准确率": format_percent(hit_count, hit_count + over_report_count),
                "召回率": format_percent(hit_count, hit_count + missed_count),
                "漏报率": format_percent(missed_count, hit_count + missed_count),
                "说明": "与人工标注逐条匹配后的结果",
            }
        )

    for scope, rows in result.items():
        grouped: dict[str, list[dict[str, str | int]]] = {}
        for row in rows:
            grouped.setdefault(str(row["合同"]), []).append(row)

        scope_rows: list[dict[str, str | int]] = []
        total_manual = 0
        total_predicted = 0
        total_hit = 0
        total_over_report = 0
        total_missed = 0

        for contract in sorted(grouped.keys()):
            contract_rows = grouped[contract]
            manual_count = int(contract_rows[0]["人工确认风险点数"])
            scope_rows.append(
                {
                    "合同": contract,
                    "对象": "人工标注",
                    "人工确认风险点数": manual_count,
                    "识别风险点数": "-",
                    "预测正确数": "-",
                    "多报数": "-",
                    "漏报数": "-",
                    "准确率": "-",
                    "召回率": "-",
                    "漏报率": "-",
                    "说明": "基准答案，不参与预测评分",
                }
            )
            scope_rows.extend(sorted(contract_rows, key=lambda item: str(item["对象"])))

            total_manual += manual_count
            for row in contract_rows:
                total_predicted += int(row["识别风险点数"])
                total_hit += int(row["预测正确数"])
                total_over_report += int(row["多报数"])
                total_missed += int(row["漏报数"])

        scope_rows.append(
            {
                "合同": "总计",
                "对象": "人工标注",
                "人工确认风险点数": total_manual,
                "识别风险点数": "-",
                "预测正确数": "-",
                "多报数": "-",
                "漏报数": "-",
                "准确率": "-",
                "召回率": "-",
                "漏报率": "-",
                "说明": "三份合同人工确认风险点总数",
            }
        )

        for party in ("本地模型", "第三方平台"):
            party_rows = [row for row in rows if row["对象"] == party]
            hit_count = sum(int(row["预测正确数"]) for row in party_rows)
            over_report_count = sum(int(row["多报数"]) for row in party_rows)
            missed_count = sum(int(row["漏报数"]) for row in party_rows)
            predicted_count = sum(int(row["识别风险点数"]) for row in party_rows)
            manual_count = sum(int(row["人工确认风险点数"]) for row in party_rows)
            scope_rows.append(
                {
                    "合同": "总计",
                    "对象": party,
                    "人工确认风险点数": manual_count,
                    "识别风险点数": predicted_count,
                    "预测正确数": hit_count,
                    "多报数": over_report_count,
                    "漏报数": missed_count,
                    "准确率": format_percent(hit_count, hit_count + over_report_count),
                    "召回率": format_percent(hit_count, hit_count + missed_count),
                    "漏报率": format_percent(missed_count, hit_count + missed_count),
                    "说明": "三份合同汇总",
                }
            )

        result[scope] = scope_rows

    return result


def column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def make_inline_cell(cell_ref: str, value: str) -> str:
    return (
        f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    )


def make_sheet_xml(headers: list[str], rows: list[list[str]]) -> str:
    sheet_rows: list[str] = []
    all_rows = [headers] + rows

    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{column_name(col_index)}{row_index}"
            cells.append(make_inline_cell(cell_ref, value))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    last_cell = f"{column_name(len(headers))}{len(all_rows)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last_cell}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        '<sheetData>'
        f'{"".join(sheet_rows)}'
        "</sheetData>"
        "</worksheet>"
    )


def build_workbook() -> None:
    summary_rows = load_summary_rows()
    headers = [
        "合同",
        "对象",
        "人工确认风险点数",
        "识别风险点数",
        "预测正确数",
        "多报数",
        "漏报数",
        "准确率",
        "召回率",
        "漏报率",
        "说明",
    ]

    sheet_payloads = {
        "口径A汇总": [
            [str(row[header]) for header in headers]
            for row in summary_rows["口径A（仅采纳 + 部分采纳）"]
        ],
        "口径B汇总": [
            [str(row[header]) for header in headers]
            for row in summary_rows["口径B（全部标签）"]
        ],
        "说明": [
            ["字段", "含义"],
            ["预测正确数", "原报告中的 TP，表示识别结果与人工标注成功匹配的风险点数量"],
            ["多报数", "原报告中的 FP，表示识别出来但人工标注中没有对应项的数量"],
            ["漏报数", "原报告中的 FN，表示人工标注中有但识别结果没有报出的数量"],
            ["准确率", "预测正确数 / (预测正确数 + 多报数)"],
            ["召回率", "预测正确数 / (预测正确数 + 漏报数)"],
            ["漏报率", "漏报数 / (预测正确数 + 漏报数)"],
            ["口径A", "仅统计“采纳”和“部分采纳”的人工标注风险点"],
            ["口径B", "统计“采纳”“部分采纳”“未采纳”的全部人工标注风险点"],
            ["数据来源", str(SOURCE_MD)],
        ],
    }

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="口径A汇总" sheetId="1" r:id="rId1"/>'
        '<sheet name="口径B汇总" sheetId="2" r:id="rId2"/>'
        '<sheet name="说明" sheetId="3" r:id="rId3"/>'
        "</sheets>"
        "</workbook>"
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>'
        '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )

    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>Codex</dc:creator>"
        "<cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )

    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Codex</Application>"
        "</Properties>"
    )

    OUTPUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT_XLSX, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("docProps/core.xml", core_xml)
        zf.writestr("docProps/app.xml", app_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", styles_xml)
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            make_sheet_xml(headers, sheet_payloads["口径A汇总"]),
        )
        zf.writestr(
            "xl/worksheets/sheet2.xml",
            make_sheet_xml(headers, sheet_payloads["口径B汇总"]),
        )
        zf.writestr(
            "xl/worksheets/sheet3.xml",
            make_sheet_xml(
                sheet_payloads["说明"][0],
                sheet_payloads["说明"][1:],
            ),
        )


if __name__ == "__main__":
    build_workbook()
    print(OUTPUT_XLSX)
