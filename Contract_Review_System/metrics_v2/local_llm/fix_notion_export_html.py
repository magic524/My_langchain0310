from __future__ import annotations

import argparse
import re
from pathlib import Path


EXTRA_CSS = """
<style id="notion-reading-fix">
html {
  background: #fbfbfa;
}

body {
  margin: 0 auto !important;
  padding: 24px 24px 56px !important;
  max-width: min(1680px, calc(100vw - 32px)) !important;
  background: #fbfbfa;
}

.page {
  width: 100%;
  max-width: none !important;
}

.page-body,
.page-body > div,
.indented,
details,
details > .indented {
  width: 100%;
  max-width: 100%;
}

details > summary {
  cursor: default;
}

table.simple-table,
table.simple-table tbody,
table.simple-table thead {
  width: 100% !important;
}

table.simple-table {
  display: table;
  table-layout: fixed;
  border-left: 1px solid rgba(55, 53, 47, 0.09);
  border-right: 1px solid rgba(55, 53, 47, 0.09);
  margin: 14px 0 20px;
}

table.simple-table th,
table.simple-table td {
  width: auto !important;
  min-width: 0 !important;
  max-width: none !important;
  vertical-align: top;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  padding: 0.45em 0.6em;
}

.semantic-green {
  color: #1f7a4f !important;
}

.semantic-red {
  color: #c4554d !important;
}

.semantic-orange {
  color: #c2752d !important;
}

.semantic-blue {
  color: #2f6fb6 !important;
}

.note-green {
  color: #1f7a4f !important;
}

.note-red {
  color: #c4554d !important;
}

.note-orange {
  color: #c2752d !important;
}

.note-blue {
  color: #2f6fb6 !important;
}

@media only screen and (max-width: 1100px) {
  body {
    padding: 16px 12px 40px !important;
    max-width: calc(100vw - 8px) !important;
  }

  h1.page-title {
    font-size: 2rem;
  }

  table.simple-table th,
  table.simple-table td {
    font-size: 13px;
    padding: 0.35em 0.45em;
  }
}
</style>
"""


EXTRA_SCRIPT = """
<script id="notion-reading-fix-script">
(function () {
  function cleanText(node) {
    return (node && node.textContent ? node.textContent : "").replace(/\\s+/g, " ").trim();
  }

  function isBlankCell(text) {
    return !text || text === "　";
  }

  function countColumns(table) {
    const rows = Array.from(table.querySelectorAll("tr"));
    return rows.reduce((max, row) => Math.max(max, row.children.length), 0);
  }

  function styleSemanticTable() {
    const tables = Array.from(document.querySelectorAll("table.simple-table"));
    const target = tables.find((table) => countColumns(table) >= 19);
    if (!target) {
      return;
    }

    const groups = [
      [0, 1, 2, 3],
      [5, 6, 7, 8],
      [10, 11, 12, 13],
      [15, 16, 17, 18]
    ];
    const rows = Array.from(target.querySelectorAll("tr"));
    rows.forEach((row, rowIndex) => {
      const cells = Array.from(row.children);
      groups.forEach((group, groupIndex) => {
        const groupCells = group
          .map((index) => cells[index])
          .filter((cell) => cell && !isBlankCell(cleanText(cell)));
        if (!groupCells.length) {
          return;
        }

        const hasMiss = groupCells.some((cell) => cleanText(cell).includes("未检测到"));
        if (groupIndex === 3) {
          groupCells.forEach((cell) => cell.classList.add("semantic-orange"));
          return;
        }

        if (hasMiss) {
          groupCells.forEach((cell) => cell.classList.add("semantic-red"));
          return;
        }

        if (rowIndex > 1) {
          groupCells.forEach((cell) => cell.classList.add("semantic-green"));
        }
      });
    });
  }

  function styleStatsTable() {
    const tables = Array.from(document.querySelectorAll("table.simple-table"));
    const target = tables.find((table) => cleanText(table).includes("合同审核报告结果统计") && cleanText(table).includes("第三方审核平台AlphaGPT"));
    if (!target) {
      return;
    }

    let blueMode = false;
    Array.from(target.querySelectorAll("tr")).forEach((row) => {
      const text = cleanText(row);
      if (!text) {
        return;
      }
      if (text.includes("第三方审核平台AlphaGPT")) {
        blueMode = true;
      }
      if (blueMode) {
        row.classList.add("semantic-blue");
      }
    });
  }

  function styleNotes() {
    Array.from(document.querySelectorAll("p")).forEach((node) => {
      const text = cleanText(node);
      if (text.includes("绿色字体表示")) {
        node.classList.add("note-green");
      } else if (text.includes("红色字体表示")) {
        node.classList.add("note-red");
      } else if (text.includes("橙色字体表示")) {
        node.classList.add("note-orange");
      } else if (text.includes("蓝色字体表示")) {
        node.classList.add("note-blue");
      }
    });
  }

  styleSemanticTable();
  styleStatsTable();
  styleNotes();
})();
</script>
"""


def build_output_html(source_html: str) -> str:
    """Inject a reading-friendly layout and heuristic color restoration."""
    html = re.sub(
        r"\s*<style id=\"notion-reading-fix\">.*?</style>",
        "",
        source_html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"\s*<script id=\"notion-reading-fix-script\">.*?</script>",
        "",
        html,
        flags=re.DOTALL,
    )
    if "<meta name=\"viewport\"" not in html:
        html = html.replace(
            "<head>",
            "<head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>",
            1,
        )

    if "lang=" not in html.split(">", 1)[0]:
        html = html.replace("<html>", "<html lang=\"zh-CN\">", 1)

    html = html.replace("</head>", f"{EXTRA_CSS}\n</head>", 1)

    html = html.replace("</body>", f"{EXTRA_SCRIPT}\n</body>", 1)

    return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a reading-friendly HTML from a Notion exported HTML file."
    )
    parser.add_argument("input_html", type=Path, help="Path to the original exported HTML.")
    parser.add_argument(
        "--output-html",
        type=Path,
        help="Path to the generated HTML. Defaults to *_阅读版.html next to the input file.",
    )
    args = parser.parse_args()

    input_html: Path = args.input_html
    output_html = args.output_html or input_html.with_name(f"{input_html.stem}_阅读版.html")

    source_html = input_html.read_text(encoding="utf-8")
    fixed_html = build_output_html(source_html)
    output_html.write_text(fixed_html, encoding="utf-8")

    print(output_html)


if __name__ == "__main__":
    main()
