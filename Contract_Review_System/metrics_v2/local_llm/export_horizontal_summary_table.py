from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


BASE_DIR = Path(
    "Contract_Review_System/metrics_v2/local_llm/outputs_fix2/"
    "20260317_word2md_eval_third_party_fix2_20260318/细节对比_fix"
)
SOURCE_MD = BASE_DIR / "20260317_word2md_eval_总体汇总.md"
OUTPUT_XLSX = BASE_DIR / "20260317_word2md_eval_横向汇总表.xlsx"

DETAIL_ROW_RE = re.compile(
    r"^\| (?P<contract>[^|]+?) \| (?P<party>本地模型|第三方平台) \| "
    r"(?P<scope>口径A（仅采纳 \+ 部分采纳）|口径B（全部标签）) \| "
    r"(?P<clause>[^|]+?) \| (?P<clause_f1>[^|]+?) \| "
    r"(?P<risk>\d+/\d+/\d+) \| (?P<risk_f1>[^|]+?) \|$"
)

SCOPE_LABELS = {
    "口径A（仅采纳 + 部分采纳）": "人工采纳的风险点",
    "口径B（全部标签）": "第三方查看的风险点",
}

PARTY_ORDER = ["本地模型", "第三方平台"]
SCOPE_ORDER = ["口径A（仅采纳 + 部分采纳）", "口径B（全部标签）"]


@dataclass(frozen=True)
class SummaryRow:
    contract: str
    party: str
    scope: str
    label_count: int
    pred_count: int
    tp: int
    fp: int
    fn: int


def parse_triplet(value: str) -> tuple[int, int, int]:
    parts = value.strip().split("/")
    return int(parts[0]), int(parts[1]), int(parts[2])


def load_rows() -> tuple[list[str], dict[tuple[str, str, str], SummaryRow]]:
    text = SOURCE_MD.read_text(encoding="utf-8")
    rows: dict[tuple[str, str, str], SummaryRow] = {}
    contract_order: list[str] = []

    for line in text.splitlines():
        match = DETAIL_ROW_RE.match(line.strip())
        if not match:
            continue

        contract = match.group("contract")
        party = match.group("party")
        scope = match.group("scope")
        tp, fp, fn = parse_triplet(match.group("risk"))

        if contract not in contract_order:
            contract_order.append(contract)

        rows[(contract, party, scope)] = SummaryRow(
            contract=contract,
            party=party,
            scope=scope,
            label_count=tp + fn,
            pred_count=tp + fp,
            tp=tp,
            fp=fp,
            fn=fn,
        )

    return contract_order, rows


def column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def make_num_fmt(num_fmt_id: int, code: str) -> str:
    return f'<numFmt numFmtId="{num_fmt_id}" formatCode="{escape(code)}"/>'


def make_font(size: int = 11, *, bold: bool = False) -> str:
    bold_tag = "<b/>" if bold else ""
    return (
        "<font>"
        f"{bold_tag}"
        f"<sz val=\"{size}\"/>"
        "<color theme=\"1\"/>"
        "<name val=\"Calibri\"/>"
        "<family val=\"2\"/>"
        "</font>"
    )


def make_fill(pattern_type: str, fg_rgb: str | None = None) -> str:
    if fg_rgb is None:
        return f'<fill><patternFill patternType="{pattern_type}"/></fill>'
    return (
        "<fill>"
        f'<patternFill patternType="{pattern_type}">'
        f'<fgColor rgb="{fg_rgb}"/>'
        '<bgColor indexed="64"/>'
        "</patternFill>"
        "</fill>"
    )


def make_border() -> str:
    side = '<left style="thin"><color auto="1"/></left>'
    return (
        "<border>"
        f"{side}"
        '<right style="thin"><color auto="1"/></right>'
        '<top style="thin"><color auto="1"/></top>'
        '<bottom style="thin"><color auto="1"/></bottom>'
        "<diagonal/>"
        "</border>"
    )


def make_xf(
    *,
    font_id: int,
    fill_id: int,
    border_id: int,
    apply_alignment: bool = True,
    horizontal: str = "center",
    vertical: str = "center",
    wrap_text: bool = False,
) -> str:
    alignment = (
        f'<alignment horizontal="{horizontal}" vertical="{vertical}"'
        + (' wrapText="1"' if wrap_text else "")
        + "/>"
    )
    return (
        '<xf numFmtId="0" fontId="{font_id}" fillId="{fill_id}" borderId="{border_id}" '
        'xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="{apply_alignment}">'
        "{alignment}</xf>"
    ).format(
        font_id=font_id,
        fill_id=fill_id,
        border_id=border_id,
        apply_alignment=1 if apply_alignment else 0,
        alignment=alignment,
    )


def styles_xml() -> str:
    fonts = [
        make_font(),
        make_font(bold=True),
    ]
    fills = [
        make_fill("none"),
        make_fill("gray125"),
        make_fill("solid", "FFD9EAF7"),
        make_fill("solid", "FFE2F0D9"),
    ]
    borders = [make_border()]
    cell_xfs = [
        make_xf(font_id=0, fill_id=0, border_id=0),
        make_xf(font_id=1, fill_id=2, border_id=0, wrap_text=True),
        make_xf(font_id=1, fill_id=3, border_id=0, wrap_text=True),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<numFmts count=\"0\"/>"
        f"<fonts count=\"{len(fonts)}\">{''.join(fonts)}</fonts>"
        f"<fills count=\"{len(fills)}\">{''.join(fills)}</fills>"
        f"<borders count=\"{len(borders)}\">{''.join(borders)}</borders>"
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        f"<cellXfs count=\"{len(cell_xfs)}\">{''.join(cell_xfs)}</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def inline_str_cell(cell_ref: str, value: str, style_id: int) -> str:
    return (
        f'<c r="{cell_ref}" s="{style_id}" t="inlineStr">'
        f"<is><t>{escape(value)}</t></is>"
        "</c>"
    )


def worksheet_xml(contract_order: list[str], rows: dict[tuple[str, str, str], SummaryRow]) -> str:
    row_xml: list[str] = []
    merges: list[str] = []

    columns = [
        14, 14,
        12, 10, 12, 10, 10,
        12, 10, 12, 10, 10,
        12, 10, 12, 10, 10,
    ]
    cols_xml = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
        for idx, width in enumerate(columns, start=1)
    )

    def add_row(row_idx: int, values: list[tuple[str, int]]) -> None:
        cells: list[str] = []
        for col_idx, (value, style_id) in enumerate(values, start=1):
            if value == "":
                continue
            cells.append(inline_str_cell(f"{column_name(col_idx)}{row_idx}", value, style_id))
        row_xml.append(f'<row r="{row_idx}" ht="24" customHeight="1">{"".join(cells)}</row>')

    header1: list[tuple[str, int]] = [("测试方式", 1), ("模型/口径", 1)]
    for contract in contract_order:
        header1.extend([(contract, 1), ("", 1), ("", 1), ("", 1), ("", 1)])
    add_row(1, header1)

    metric_headers = ["标签数", "预测数", "风险点预测命中", "风险点误报", "风险点漏报"]
    header2: list[tuple[str, int]] = [("", 1), ("", 1)]
    for _ in contract_order:
        header2.extend((metric, 1) for metric in metric_headers)
    add_row(2, header2)

    merges.extend(["A1:A2", "B1:B2"])
    for group_index in range(len(contract_order)):
        start_col = 3 + group_index * 5
        end_col = start_col + 4
        merges.append(f"{column_name(start_col)}1:{column_name(end_col)}1")

    current_row = 3
    for scope in SCOPE_ORDER:
        merges.append(f"A{current_row}:A{current_row + 1}")
        add_row(
            current_row,
            [
                (SCOPE_LABELS[scope], 2),
                ("本地模型", 0),
                *build_data_cells(contract_order, rows, "本地模型", scope),
            ],
        )
        add_row(
            current_row + 1,
            [
                ("", 2),
                ("第三方平台", 0),
                *build_data_cells(contract_order, rows, "第三方平台", scope),
            ],
        )
        current_row += 2

    merge_xml = "".join(f'<mergeCell ref="{ref}"/>' for ref in merges)
    last_cell = f"{column_name(2 + len(contract_order) * 5)}{current_row - 1}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last_cell}"/>'
        "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"18\"/>"
        f"<cols>{cols_xml}</cols>"
        f"<sheetData>{''.join(row_xml)}</sheetData>"
        f'<mergeCells count="{len(merges)}">{merge_xml}</mergeCells>'
        '<pageMargins left="0.5" right="0.5" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        "</worksheet>"
    )


def build_data_cells(
    contract_order: list[str],
    rows: dict[tuple[str, str, str], SummaryRow],
    party: str,
    scope: str,
) -> list[tuple[str, int]]:
    values: list[tuple[str, int]] = []
    for contract in contract_order:
        row = rows[(contract, party, scope)]
        values.extend(
            [
                (str(row.label_count), 0),
                (str(row.pred_count), 0),
                (str(row.tp), 0),
                (str(row.fp), 0),
                (str(row.fn), 0),
            ]
        )
    return values


def workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="横向汇总" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )


def workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Microsoft Excel</Application>"
        "</Properties>"
    )


def core_xml() -> str:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>Codex</dc:creator>"
        "<cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def build_workbook() -> None:
    contract_order, rows = load_rows()
    OUTPUT_XLSX.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(OUTPUT_XLSX, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml())
        archive.writestr("_rels/.rels", root_rels_xml())
        archive.writestr("docProps/app.xml", app_xml())
        archive.writestr("docProps/core.xml", core_xml())
        archive.writestr("xl/workbook.xml", workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
        archive.writestr("xl/styles.xml", styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml(contract_order, rows))


if __name__ == "__main__":
    build_workbook()
    print(OUTPUT_XLSX)
