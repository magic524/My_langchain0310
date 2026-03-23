from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


BODY_RE = re.compile(r"<body[^>]*>(?P<body>.*)</body>", re.IGNORECASE | re.DOTALL)
TITLE_RE = re.compile(
    r'<h1 class="page-title"[^>]*>(?P<title>.*?)</h1>', re.IGNORECASE | re.DOTALL
)
STYLE_RE = re.compile(r"<style>.*?</style>", re.IGNORECASE | re.DOTALL)
TOGGLE_OPEN_RE = re.compile(r'<ul[^>]*class="toggle"[^>]*>\s*<li>', re.IGNORECASE)
TOGGLE_CLOSE_RE = re.compile(r"</li>\s*</ul>", re.IGNORECASE)
DETAILS_TOKEN_RE = re.compile(
    r"(?P<open><details\b[^>]*>)|"
    r"(?P<close></details>)|"
    r"(?P<summary><summary\b[^>]*>.*?</summary>)",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
SUMMARY_TEXT_RE = re.compile(r"<summary\b[^>]*>(?P<text>.*?)</summary>", re.IGNORECASE | re.DOTALL)

WORD_STYLE = """
<style>
html, body {
  margin: 0;
  padding: 0;
  font-family: "Microsoft YaHei", "SimSun", Calibri, sans-serif;
  color: #222;
}
body {
  margin: 24px;
  line-height: 1.6;
  font-size: 11pt;
}
h1, h2, h3, h4 {
  page-break-after: avoid;
  margin-top: 18px;
  margin-bottom: 8px;
  line-height: 1.3;
}
h1 { font-size: 20pt; }
h2 { font-size: 16pt; }
h3 { font-size: 13pt; }
h4 { font-size: 11.5pt; }
p, li {
  margin-top: 6px;
  margin-bottom: 6px;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0 16px 0;
  table-layout: fixed;
}
th, td {
  border: 1px solid #999;
  padding: 6px 8px;
  vertical-align: top;
  text-align: left;
  word-break: break-word;
}
th {
  background: #f2f2f2;
  font-weight: 700;
}
.section-block {
  margin-bottom: 12px;
}
.page-title {
  margin-top: 0;
  margin-bottom: 12px;
}
</style>
""".strip()


def _strip_tags(fragment: str) -> str:
    text = TAG_RE.sub("", fragment)
    return html.unescape(text).strip()


def _summary_to_heading(summary_html: str, depth: int) -> str:
    match = SUMMARY_TEXT_RE.search(summary_html)
    text = _strip_tags(match.group("text") if match else summary_html)
    heading_level = min(depth + 1, 4)
    return f"<h{heading_level}>{html.escape(text)}</h{heading_level}>"


def _flatten_details(html_text: str) -> str:
    html_text = TOGGLE_OPEN_RE.sub("", html_text)
    html_text = TOGGLE_CLOSE_RE.sub("", html_text)

    parts: list[str] = []
    cursor = 0
    depth = 0
    for match in DETAILS_TOKEN_RE.finditer(html_text):
        parts.append(html_text[cursor : match.start()])
        if match.group("open"):
            depth += 1
            parts.append('<div class="section-block">')
        elif match.group("summary"):
            parts.append(_summary_to_heading(match.group("summary"), depth))
        elif match.group("close"):
            parts.append("</div>")
            depth = max(depth - 1, 0)
        cursor = match.end()
    parts.append(html_text[cursor:])
    return "".join(parts)


def convert_html(source_path: Path, output_path: Path) -> None:
    source_text = source_path.read_text(encoding="utf-8")
    body_match = BODY_RE.search(source_text)
    if body_match is None:
        raise ValueError(f"Could not find <body> in {source_path}")

    body_html = body_match.group("body")
    body_html = _flatten_details(body_html)

    title_match = TITLE_RE.search(source_text)
    title_text = _strip_tags(title_match.group("title")) if title_match else source_path.stem

    output_text = (
        "<html><head>"
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>'
        f"<title>{html.escape(title_text)}</title>"
        f"{WORD_STYLE}"
        "</head><body>"
        f"{body_html}"
        "</body></html>"
    )
    output_path.write_text(output_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten Notion HTML for Word-friendly viewing")
    parser.add_argument("--input", required=True, help="Source Notion-exported HTML path")
    parser.add_argument("--output", required=True, help="Output flattened HTML path")
    args = parser.parse_args()

    convert_html(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
