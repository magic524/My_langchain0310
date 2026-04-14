"""Use `mammoth` to convert DOCX files into review-friendly Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

_CHINESE_NUMERALS = "零一二三四五六七八九十百千"
_EXPLICIT_CHINESE_MAJOR_HEADING_RE = re.compile(
    rf"^\*\*(?P<number>[{_CHINESE_NUMERALS}]+)[、.．](?P<title>.+)\*\*$"
)
_EXPLICIT_ARABIC_MAJOR_HEADING_RE = re.compile(r"^\*\*(?P<number>\d+)[、.．]\s*(?P<title>.+)\*\*$")
_GENERATED_LIST_HEADING_RE = re.compile(r"^(?P<index>\d+)\.\s+\*\*(?P<title>.+)\*\*$")


def is_mammoth_available() -> bool:
    """Return whether `mammoth` can be imported in the current runtime."""

    try:
        import mammoth  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def import_mammoth() -> Any:
    """Import `mammoth` with a friendly error message."""

    try:
        import mammoth  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "无法导入 mammoth，请先进入 `langchain` 环境并安装依赖："
            "`conda activate langchain && pip install mammoth`"
        ) from exc
    return mammoth


def _collapse_inline_whitespace(text: str) -> str:
    """Collapse inline whitespace while preserving Markdown control characters."""

    collapsed = re.sub(r"[ \t\r\f\v]+", " ", text)
    collapsed = re.sub(r" ?\n ?", "\n", collapsed)
    return collapsed.strip()


@dataclass(slots=True)
class MammothConversionResult:
    """Markdown converted from a DOCX file via `mammoth`."""

    markdown: str
    warning_text: str


class _HtmlToMarkdownParser(HTMLParser):
    """Convert a limited subset of HTML into contract-friendly Markdown."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.current_parts: list[str] = []
        self.list_stack: list[dict[str, int | str]] = []
        self.in_table = False
        self.table_rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell_parts: list[str] | None = None
        self.major_heading_style: str | None = None
        self.major_heading_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening HTML tags."""

        del attrs
        if tag in {"p", "div"}:
            self._flush_block()
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()
            level = int(tag[1])
            self.current_parts.append(f"{'#' * level} ")
            return
        if tag in {"strong", "b"}:
            self._append_inline("**")
            return
        if tag in {"em", "i"}:
            self._append_inline("*")
            return
        if tag == "br":
            self._append_inline("  \n")
            return
        if tag in {"ul", "ol"}:
            self.list_stack.append({"type": tag, "index": 0})
            return
        if tag == "li":
            self._flush_block()
            if self.list_stack and self.list_stack[-1]["type"] == "ol":
                self.list_stack[-1]["index"] = int(self.list_stack[-1]["index"]) + 1
                prefix = f"{self.list_stack[-1]['index']}. "
            else:
                prefix = "- "
            self.current_parts.append(prefix)
            return
        if tag == "table":
            self._flush_block()
            self.in_table = True
            self.table_rows = []
            return
        if tag == "tr":
            self.current_row = []
            return
        if tag in {"td", "th"}:
            self.current_cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        """Handle closing HTML tags."""

        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()
            return
        if tag in {"strong", "b"}:
            self._append_inline("**")
            return
        if tag in {"em", "i"}:
            self._append_inline("*")
            return
        if tag in {"ul", "ol"}:
            if self.list_stack:
                self.list_stack.pop()
            self._flush_block()
            return
        if tag in {"td", "th"}:
            if self.current_row is not None and self.current_cell_parts is not None:
                cell_text = _collapse_inline_whitespace("".join(self.current_cell_parts))
                self.current_row.append(cell_text)
            self.current_cell_parts = None
            return
        if tag == "tr":
            if self.current_row:
                self.table_rows.append(self.current_row)
            self.current_row = None
            return
        if tag == "table":
            self._flush_table()
            self.in_table = False

    def handle_data(self, data: str) -> None:
        """Handle text data."""

        if not data:
            return
        self._append_inline(data)

    def get_markdown(self) -> str:
        """Return the final Markdown output."""

        self._flush_block()
        self._flush_table()
        return "\n\n".join(block for block in self.blocks if block.strip()).strip() + "\n"

    def _append_inline(self, text: str) -> None:
        """Append text to the active inline buffer."""

        if self.current_cell_parts is not None:
            self.current_cell_parts.append(text)
            return
        self.current_parts.append(text)

    def _flush_block(self) -> None:
        """Flush the current block buffer."""

        text = _collapse_inline_whitespace("".join(self.current_parts))
        text = self._normalize_contract_heading(text)
        if text:
            self.blocks.append(text)
            self._remember_major_heading(text)
        self.current_parts = []

    def _flush_table(self) -> None:
        """Flush the currently collected HTML table as Markdown."""

        if not self.table_rows:
            return

        max_columns = max(len(row) for row in self.table_rows)
        normalized_rows = [row + [""] * (max_columns - len(row)) for row in self.table_rows]
        header = normalized_rows[0]
        separator = ["---"] * max_columns
        rendered_rows = [
            "| " + " | ".join(cell or " " for cell in header) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for row in normalized_rows[1:]:
            rendered_rows.append("| " + " | ".join(cell or " " for cell in row) + " |")

        self.blocks.append("\n".join(rendered_rows))
        self.table_rows = []

    def _normalize_contract_heading(self, text: str) -> str:
        """Normalize list-rendered contract headings back into heading text."""

        match = _GENERATED_LIST_HEADING_RE.match(text)
        if not match:
            return text

        title = match.group("title").strip()
        if not self._looks_like_heading_title(title):
            return text

        next_heading = self._format_next_major_heading(title)
        if next_heading is None:
            return text
        return f"**{next_heading}**"

    def _looks_like_heading_title(self, text: str) -> bool:
        """Return whether a short bold list item resembles a contract heading."""

        normalized = text.strip().strip("*").strip()
        if not normalized:
            return False
        if len(normalized) > 32:
            return False
        if any(mark in normalized for mark in "。；！？"):
            return False
        if normalized.startswith(("一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、")):
            return False
        if re.match(r"^\d+(?:[.．、]\d+)+", normalized):
            return False
        cjk_count = sum(1 for char in normalized if "\u4e00" <= char <= "\u9fff")
        return cjk_count >= 2

    def _format_next_major_heading(self, title: str) -> str | None:
        """Format the next major heading based on previous explicit headings."""

        if self.major_heading_style == "chinese":
            next_index = self.major_heading_index + 1
            return f"{_int_to_chinese(next_index)}、{title}"
        if self.major_heading_style == "arabic":
            next_index = self.major_heading_index + 1
            return f"{next_index}. {title}"
        return None

    def _remember_major_heading(self, text: str) -> None:
        """Track explicit major heading numbering style from emitted Markdown."""

        chinese_match = _EXPLICIT_CHINESE_MAJOR_HEADING_RE.match(text)
        if chinese_match:
            self.major_heading_style = "chinese"
            self.major_heading_index = _chinese_to_int(chinese_match.group("number"))
            return

        arabic_match = _EXPLICIT_ARABIC_MAJOR_HEADING_RE.match(text)
        if arabic_match:
            self.major_heading_style = "arabic"
            self.major_heading_index = int(arabic_match.group("number"))


def _chinese_to_int(text: str) -> int:
    """Convert a simple Chinese numeral string into an integer."""

    mapping = {
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if text == "十":
        return 10
    if "十" not in text:
        total = 0
        for char in text:
            total = total * 10 + mapping[char]
        return total
    left, _, right = text.partition("十")
    tens = mapping[left] if left else 1
    ones = mapping[right] if right else 0
    return tens * 10 + ones


def _int_to_chinese(value: int) -> str:
    """Convert integers in a small range into Chinese numerals."""

    mapping = {
        0: "零",
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
    }
    if value <= 10:
        return "十" if value == 10 else mapping[value]
    if value < 20:
        return "十" + mapping[value % 10]
    tens, ones = divmod(value, 10)
    if ones == 0:
        return mapping[tens] + "十"
    return mapping[tens] + "十" + mapping[ones]


def html_to_markdown(html_text: str) -> str:
    """Convert `mammoth` HTML output into lightweight Markdown."""

    parser = _HtmlToMarkdownParser()
    parser.feed(html_text)
    parser.close()
    return parser.get_markdown()


def convert_docx_to_markdown(docx_path: Path) -> MammothConversionResult:
    """Convert a DOCX file into Markdown via `mammoth`."""

    mammoth = import_mammoth()
    with docx_path.open("rb") as handle:
        result = mammoth.convert_to_html(handle)

    markdown = html_to_markdown(result.value)
    warning_text = "\n".join(message.message for message in result.messages if getattr(message, "message", "").strip())
    return MammothConversionResult(markdown=markdown, warning_text=warning_text)
