from __future__ import annotations

from dataclasses import dataclass
import html
import re
from pathlib import Path


_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_MARKDOWN_ESCAPE_PATTERN = re.compile(r"\\([\\`*_{}\[\]()#+.!|\-])")
_SEPARATOR_CHARS = {"|", ":", "-", " "}
_BREAK_TOKEN = "__HTML_BREAK__"


@dataclass(frozen=True)
class MarkdownTable:
    """A parsed Markdown table."""

    headers: list[str]
    rows: list[list[str]]


def convert_markdown_file_to_html(markdown_path: Path, html_path: Path) -> None:
    """Convert a Markdown report into a styled HTML table document.

    Args:
        markdown_path: Source Markdown file path.
        html_path: Target HTML file path.
    """

    markdown_text = markdown_path.read_text(encoding="utf-8")
    html_text = markdown_to_html_document(markdown_text)
    html_path.write_text(html_text, encoding="utf-8")


def markdown_to_html_document(markdown_text: str) -> str:
    """Render a lightweight Markdown report as an HTML document.

    The renderer intentionally focuses on the constructs used by the contract
    comparison reports: headings, bullet lists, paragraphs, and pipe tables.

    Args:
        markdown_text: Markdown source text.

    Returns:
        A complete HTML document string.
    """

    blocks = _render_blocks(markdown_text.splitlines())
    title = _extract_title(markdown_text) or "Markdown Table Export"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f6f9;
      --panel: #ffffff;
      --text: #1c2430;
      --muted: #5a6678;
      --line: #d7dde7;
      --head: #edf3fb;
      --accent: #1c5fa8;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #eef4fb 0%, var(--bg) 240px);
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
      line-height: 1.6;
    }}
    main {{
      max-width: 1800px;
      margin: 0 auto;
      padding: 24px;
    }}
    .sheet {{
      background: var(--panel);
      border-radius: 16px;
      box-shadow: 0 12px 32px rgba(28, 36, 48, 0.08);
      padding: 28px 32px;
      overflow: hidden;
    }}
    h1, h2, h3, h4, h5, h6 {{
      color: var(--accent);
      margin: 1.25em 0 0.55em;
      line-height: 1.3;
    }}
    h1 {{
      margin-top: 0;
      font-size: 30px;
    }}
    h2 {{
      font-size: 24px;
      border-bottom: 2px solid #e6edf7;
      padding-bottom: 6px;
    }}
    h3 {{
      font-size: 20px;
    }}
    p, li {{
      font-size: 14px;
    }}
    p {{
      margin: 0.45em 0 0.8em;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    ul {{
      margin: 0.5em 0 1em 1.25em;
      padding: 0;
    }}
    code {{
      font-family: "Consolas", "Courier New", monospace;
      background: #f2f4f8;
      border-radius: 4px;
      padding: 1px 5px;
      font-size: 0.95em;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 12px 0 28px;
      border: 1px solid var(--line);
      border-radius: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      background: #fff;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 10px 12px;
      vertical-align: top;
      text-align: left;
      font-size: 13px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    th {{
      background: var(--head);
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <main>
    <section class="sheet">
{blocks}
    </section>
  </main>
</body>
</html>
"""


def _extract_title(markdown_text: str) -> str | None:
    for line in markdown_text.splitlines():
        match = _HEADING_PATTERN.match(line.strip())
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return None


def _render_blocks(lines: list[str]) -> str:
    fragments: list[str] = []
    index = 0
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            fragments.append("      </ul>")
            in_list = False

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped:
            close_list()
            index += 1
            continue

        heading_match = _HEADING_PATTERN.match(stripped)
        if heading_match:
            close_list()
            level = len(heading_match.group(1))
            content = _format_inline(heading_match.group(2).strip())
            fragments.append(f"      <h{level}>{content}</h{level}>")
            index += 1
            continue

        if _is_table_start(lines, index):
            close_list()
            table, consumed = _parse_table(lines, index)
            fragments.append(_render_table(table))
            index += consumed
            continue

        if stripped.startswith("- "):
            if not in_list:
                fragments.append("      <ul>")
                in_list = True
            fragments.append(f"        <li>{_format_inline(stripped[2:].strip())}</li>")
            index += 1
            continue

        close_list()
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate:
                break
            if _HEADING_PATTERN.match(candidate):
                break
            if candidate.startswith("- "):
                break
            if _is_table_start(lines, index):
                break
            paragraph_lines.append(candidate)
            index += 1
        fragments.append(f"      <p>{_format_inline(' '.join(paragraph_lines))}</p>")

    close_list()
    return "\n".join(fragments)


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    first = lines[index].strip()
    second = lines[index + 1].strip()
    if "|" not in first or "|" not in second:
        return False
    return _is_separator_row(second)


def _is_separator_row(line: str) -> bool:
    stripped = line.strip().strip("|")
    return bool(stripped) and all(char in _SEPARATOR_CHARS for char in stripped)


def _parse_table(lines: list[str], start_index: int) -> tuple[MarkdownTable, int]:
    raw_rows: list[str] = []
    index = start_index
    while index < len(lines):
        candidate = lines[index].strip()
        if not candidate.startswith("|"):
            break
        raw_rows.append(candidate)
        index += 1

    headers = _split_markdown_row(raw_rows[0])
    body_rows = [_split_markdown_row(row) for row in raw_rows[2:]]
    normalized_rows = [_normalize_row(row, len(headers)) for row in body_rows]
    return MarkdownTable(headers=headers, rows=normalized_rows), index - start_index


def _split_markdown_row(row: str) -> list[str]:
    stripped = row.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            current.append(char)
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def _normalize_row(row: list[str], width: int) -> list[str]:
    if len(row) < width:
        return row + [""] * (width - len(row))
    if len(row) > width:
        return row[: width - 1] + [" | ".join(row[width - 1 :])]
    return row


def _render_table(table: MarkdownTable) -> str:
    head = "".join(f"<th>{_format_inline(cell)}</th>" for cell in table.headers)
    body_rows = []
    for row in table.rows:
        cells = "".join(f"<td>{_format_inline(cell)}</td>" for cell in row)
        body_rows.append(f"          <tr>{cells}</tr>")
    body = "\n".join(body_rows)
    return (
        "      <div class=\"table-wrap\">\n"
        "        <table>\n"
        f"          <thead><tr>{head}</tr></thead>\n"
        f"          <tbody>\n{body}\n          </tbody>\n"
        "        </table>\n"
        "      </div>"
    )


def _format_inline(text: str) -> str:
    normalized = text.replace("<br>", _BREAK_TOKEN).replace("<br/>", _BREAK_TOKEN)
    normalized = _MARKDOWN_ESCAPE_PATTERN.sub(r"\1", normalized)
    parts = re.split(r"(`[^`]*`)", normalized)
    rendered_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            code = html.escape(part[1:-1])
            rendered_parts.append(f"<code>{code}</code>")
            continue
        rendered_parts.append(html.escape(part))
    combined = "".join(rendered_parts)
    return combined.replace(_BREAK_TOKEN, "<br>")
