from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
MARGIN_X = 90
MARGIN_Y = 90
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_X * 2)
LINE_GAP = 8
PARAGRAPH_GAP = 10
CODE_BACKGROUND = "#f5f5f5"
TEXT_COLOR = "#202124"


@dataclass(frozen=True)
class TextStyle:
    font_path: str
    font_size: int
    indent: int = 0
    top_gap: int = 0
    bottom_gap: int = PARAGRAPH_GAP
    code_block: bool = False


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font with the requested size."""
    return ImageFont.truetype(path, size=size)


def choose_font_paths() -> tuple[str, str]:
    """Choose readable system fonts for Chinese and code-ish content."""
    sans_candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    mono_candidates = [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
    ]

    sans_path = next((path for path in sans_candidates if Path(path).exists()), None)
    mono_path = next((path for path in mono_candidates if Path(path).exists()), None)
    if sans_path is None or mono_path is None:
        msg = "Could not find a usable Windows font for PDF rendering."
        raise FileNotFoundError(msg)
    return sans_path, mono_path


def build_styles() -> dict[str, TextStyle]:
    """Create the small style palette used for rendering."""
    sans_path, mono_path = choose_font_paths()
    return {
        "body": TextStyle(font_path=sans_path, font_size=22),
        "h1": TextStyle(font_path=sans_path, font_size=34, top_gap=18, bottom_gap=14),
        "h2": TextStyle(font_path=sans_path, font_size=30, top_gap=16, bottom_gap=12),
        "h3": TextStyle(font_path=sans_path, font_size=26, top_gap=14, bottom_gap=12),
        "h4": TextStyle(font_path=sans_path, font_size=24, top_gap=12, bottom_gap=10),
        "list": TextStyle(font_path=sans_path, font_size=22, indent=28),
        "quote": TextStyle(font_path=sans_path, font_size=22, indent=28),
        "code": TextStyle(
            font_path=mono_path,
            font_size=20,
            indent=18,
            top_gap=4,
            bottom_gap=6,
            code_block=True,
        ),
    }


def normalize_text(markdown_text: str) -> list[tuple[str, TextStyle]]:
    """Convert Markdown into styled text blocks."""
    styles = build_styles()
    blocks: list[tuple[str, TextStyle]] = []
    in_code_block = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            if in_code_block:
                blocks.append(("", styles["code"]))
            continue

        if in_code_block:
            blocks.append((line if line else " ", styles["code"]))
            continue

        if not stripped:
            blocks.append(("", styles["body"]))
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            style_key = f"h{level}"
            blocks.append((heading_match.group(2).strip(), styles[style_key]))
            continue

        quote_match = re.match(r"^>\s?(.*)$", line)
        if quote_match:
            blocks.append((quote_match.group(1).strip() or " ", styles["quote"]))
            continue

        unordered_match = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if unordered_match:
            blocks.append((f"• {unordered_match.group(1).strip()}", styles["list"]))
            continue

        ordered_match = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if ordered_match:
            blocks.append((f"{ordered_match.group(1)}. {ordered_match.group(2).strip()}", styles["list"]))
            continue

        blocks.append((line, styles["body"]))

    return blocks


def wrap_text(
    text: str,
    *,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """Wrap text by visible width, keeping whitespace readable."""
    if not text:
        return [""]

    wrapped_lines: list[str] = []
    current_line = ""

    for character in text:
        candidate = current_line + character
        if draw.textlength(candidate, font=font) <= max_width:
            current_line = candidate
            continue

        if current_line:
            wrapped_lines.append(current_line)
            current_line = character
        else:
            wrapped_lines.append(character)
            current_line = ""

    if current_line:
        wrapped_lines.append(current_line)

    return wrapped_lines or [""]


def create_blank_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Create a blank white A4 page."""
    page = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
    return page, ImageDraw.Draw(page)


def render_pdf(markdown_path: Path, pdf_path: Path) -> None:
    """Render a Markdown file into a multipage PDF."""
    markdown_text = markdown_path.read_text(encoding="utf-8")
    blocks = normalize_text(markdown_text)

    pages: list[Image.Image] = []
    page, draw = create_blank_page()
    current_y = MARGIN_Y

    for text, style in blocks:
        font = load_font(style.font_path, style.font_size)
        line_height = font.size + LINE_GAP
        available_width = CONTENT_WIDTH - style.indent
        lines = wrap_text(text, draw=draw, font=font, max_width=available_width)
        block_height = style.top_gap + (line_height * len(lines)) + style.bottom_gap

        if current_y + block_height > PAGE_HEIGHT - MARGIN_Y:
            pages.append(page)
            page, draw = create_blank_page()
            current_y = MARGIN_Y

        current_y += style.top_gap
        if style.code_block and any(line for line in lines):
            code_top = current_y - 4
            code_bottom = current_y + (line_height * len(lines)) + 4
            draw.rounded_rectangle(
                (
                    MARGIN_X,
                    code_top,
                    PAGE_WIDTH - MARGIN_X,
                    code_bottom,
                ),
                radius=8,
                fill=CODE_BACKGROUND,
            )

        for line in lines:
            draw.text(
                (MARGIN_X + style.indent, current_y),
                line,
                fill=TEXT_COLOR,
                font=font,
            )
            current_y += line_height

        current_y += style.bottom_gap

    pages.append(page)
    first_page, remaining_pages = pages[0], pages[1:]
    first_page.save(pdf_path, "PDF", resolution=150.0, save_all=True, append_images=remaining_pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Markdown text into a PDF using Pillow.")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    args = parser.parse_args()
    render_pdf(args.input_path, args.output_path)


if __name__ == "__main__":
    main()
