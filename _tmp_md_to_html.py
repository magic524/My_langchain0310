from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


INLINE_CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_inline(text: str) -> str:
    """Render a small, safe subset of inline Markdown."""
    escaped_text = html.escape(text, quote=False)
    escaped_text = LINK_RE.sub(
        lambda match: (
            f'<a href="{html.escape(match.group(2), quote=True)}">'
            f"{html.escape(match.group(1), quote=False)}</a>"
        ),
        escaped_text,
    )
    escaped_text = INLINE_CODE_RE.sub(
        lambda match: f"<code>{html.escape(match.group(1), quote=False)}</code>",
        escaped_text,
    )
    escaped_text = BOLD_RE.sub(r"<strong>\1</strong>", escaped_text)
    escaped_text = ITALIC_RE.sub(r"<em>\1</em>", escaped_text)
    return escaped_text


def close_open_blocks(parts: list[str], *, in_list: bool, in_blockquote: bool) -> tuple[bool, bool]:
    """Close list and blockquote tags when the parser leaves those blocks."""
    if in_list:
        parts.append("</ul>")
        in_list = False
    if in_blockquote:
        parts.append("</blockquote>")
        in_blockquote = False
    return in_list, in_blockquote


def markdown_to_html(markdown_text: str, title: str) -> str:
    """Convert Markdown text to a simple standalone HTML document."""
    lines = markdown_text.splitlines()
    parts: list[str] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False
    in_list = False
    in_blockquote = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            paragraph = " ".join(line.strip() for line in paragraph_lines)
            parts.append(f"<p>{render_inline(paragraph)}</p>")
            paragraph_lines = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_list or in_blockquote:
                in_list, in_blockquote = close_open_blocks(
                    parts, in_list=in_list, in_blockquote=in_blockquote
                )
            if in_code_block:
                code_html = html.escape("\n".join(code_lines), quote=False)
                parts.append(f"<pre><code>{code_html}</code></pre>")
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            if in_list or in_blockquote:
                in_list, in_blockquote = close_open_blocks(
                    parts, in_list=in_list, in_blockquote=in_blockquote
                )
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            flush_paragraph()
            if in_list or in_blockquote:
                in_list, in_blockquote = close_open_blocks(
                    parts, in_list=in_list, in_blockquote=in_blockquote
                )
            level = len(heading_match.group(1))
            parts.append(f"<h{level}>{render_inline(heading_match.group(2).strip())}</h{level}>")
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            if in_list or in_blockquote:
                in_list, in_blockquote = close_open_blocks(
                    parts, in_list=in_list, in_blockquote=in_blockquote
                )
            parts.append("<hr />")
            continue

        quote_match = re.match(r"^>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            if in_list:
                in_list, in_blockquote = close_open_blocks(
                    parts, in_list=in_list, in_blockquote=in_blockquote
                )
            if not in_blockquote:
                parts.append("<blockquote>")
                in_blockquote = True
            parts.append(f"<p>{render_inline(quote_match.group(1))}</p>")
            continue

        list_match = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if list_match:
            flush_paragraph()
            if in_blockquote:
                in_list, in_blockquote = close_open_blocks(
                    parts, in_list=in_list, in_blockquote=in_blockquote
                )
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{render_inline(list_match.group(1).strip())}</li>")
            continue

        ordered_list_match = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if ordered_list_match:
            flush_paragraph()
            if in_blockquote:
                in_list, in_blockquote = close_open_blocks(
                    parts, in_list=in_list, in_blockquote=in_blockquote
                )
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{render_inline(ordered_list_match.group(1).strip())}</li>")
            continue

        paragraph_lines.append(line)

    flush_paragraph()
    if in_code_block:
        code_html = html.escape("\n".join(code_lines), quote=False)
        parts.append(f"<pre><code>{code_html}</code></pre>")
    if in_list or in_blockquote:
        in_list, in_blockquote = close_open_blocks(parts, in_list=in_list, in_blockquote=in_blockquote)

    body_html = "\n".join(parts)
    escaped_title = html.escape(title, quote=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #202124;
      --muted: #5f6368;
      --border: #dadce0;
      --code-bg: #f6f8fa;
      --page-bg: #ffffff;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: var(--page-bg);
      line-height: 1.6;
      font-size: 13px;
    }}
    main {{
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 40px 48px;
    }}
    h1, h2, h3, h4, h5, h6 {{
      margin: 1.35em 0 0.55em;
      line-height: 1.25;
    }}
    h1 {{
      font-size: 2em;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.3em;
    }}
    h2 {{
      font-size: 1.5em;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.22em;
    }}
    p, ul, ol, pre, blockquote {{
      margin: 0.7em 0;
    }}
    ul, ol {{
      padding-left: 1.5em;
    }}
    code {{
      font-family: Consolas, "Courier New", monospace;
      background: var(--code-bg);
      padding: 0.1em 0.35em;
      border-radius: 4px;
      font-size: 0.92em;
    }}
    pre {{
      background: var(--code-bg);
      padding: 14px 16px;
      border-radius: 8px;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
      border: 1px solid var(--border);
    }}
    pre code {{
      background: transparent;
      padding: 0;
      border-radius: 0;
    }}
    blockquote {{
      border-left: 4px solid var(--border);
      padding: 0.2em 1em;
      color: var(--muted);
      background: #fafafa;
    }}
    a {{
      color: #0b57d0;
      text-decoration: none;
    }}
    hr {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 1.4em 0;
    }}
    @page {{
      size: A4;
      margin: 16mm 14mm 16mm;
    }}
  </style>
</head>
<body>
  <main>
{body_html}
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Markdown file into standalone HTML.")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    args = parser.parse_args()

    markdown_text = args.input_path.read_text(encoding="utf-8")
    html_text = markdown_to_html(markdown_text, title=args.input_path.stem)
    args.output_path.write_text(html_text, encoding="utf-8")


if __name__ == "__main__":
    main()
