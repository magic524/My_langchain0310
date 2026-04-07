"""PDF to Markdown helpers for restricted office environments."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import re


def _import_pdf_reader() -> type:
    """Import a lightweight PDF reader implementation."""

    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = import_module(module_name)
        except ImportError:
            continue
        reader = getattr(module, "PdfReader", None)
        if reader is not None:
            return reader

    raise RuntimeError(
        "当前环境缺少 PDF 解析依赖，请先进入 `langchain` 环境安装："
        "`conda activate langchain && pip install pypdf`。"
    )


def _normalize_text(text: str) -> list[str]:
    """Normalize extracted PDF text into readable Markdown paragraphs."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    normalized = normalized.replace("\u3000", " ")
    chunks = [chunk.strip() for chunk in normalized.split("\n")]

    lines: list[str] = []
    for chunk in chunks:
        compact = re.sub(r"[ \t]+", " ", chunk).strip()
        if not compact:
            continue
        lines.append(compact)
    return lines


def extract_pdf_pages(pdf_path: Path) -> list[list[str]]:
    """Extract text lines page by page from a PDF."""

    reader_cls = _import_pdf_reader()
    reader = reader_cls(str(pdf_path))
    pages: list[list[str]] = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        pages.append(_normalize_text(page_text))
    return pages


def build_fallback_markdown(pdf_path: Path) -> tuple[str, dict[str, int | bool]]:
    """Build Markdown from a PDF using `pypdf`/`PyPDF2` text extraction."""

    pages = extract_pdf_pages(pdf_path)
    body_lines = [f"# {pdf_path.stem}", ""]
    non_empty_pages = 0
    total_lines = 0

    for index, lines in enumerate(pages, start=1):
        body_lines.append(f"## 第 {index} 页")
        body_lines.append("")
        if lines:
            non_empty_pages += 1
            total_lines += len(lines)
            body_lines.extend(lines)
        else:
            body_lines.append("> 本页未提取到可读文本，可能是扫描页或图片页。")
        body_lines.append("")

    if len(pages) == 0:
        body_lines.append("> 未识别到 PDF 页面内容。")
        body_lines.append("")

    markdown = "\n".join(body_lines).rstrip() + "\n"
    stats: dict[str, int | bool] = {
        "page_count": len(pages),
        "non_empty_page_count": non_empty_pages,
        "line_count": total_lines,
        "used_pypdf": True,
    }
    return markdown, stats
