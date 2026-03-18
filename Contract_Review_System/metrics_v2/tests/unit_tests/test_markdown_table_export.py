from __future__ import annotations

from pathlib import Path

from contract_metrics_v2.markdown_table_export import (
    convert_markdown_file_to_html,
    markdown_to_html_document,
)


def test_markdown_to_html_document_renders_headings_lists_and_tables() -> None:
    markdown_text = """# 示例报告

## 数据来源

- 原文件: `demo.md`

## 对照表

| 列1 | 列2 |
| --- | --- |
| 原文A | 模型A<br>建议A |
| 原文B | 模型B |
"""

    html = markdown_to_html_document(markdown_text)

    assert "<h1>示例报告</h1>" in html
    assert "<h2>数据来源</h2>" in html
    assert "<li>原文件: <code>demo.md</code></li>" in html
    assert "<table>" in html
    assert "<th>列1</th>" in html
    assert "模型A<br>建议A" in html


def test_convert_markdown_file_to_html_writes_document(tmp_path: Path) -> None:
    markdown_path = tmp_path / "sample.md"
    html_path = tmp_path / "sample.html"
    markdown_path.write_text(
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n",
        encoding="utf-8",
    )

    convert_markdown_file_to_html(markdown_path, html_path)

    html = html_path.read_text(encoding="utf-8")
    assert html_path.exists()
    assert "<!DOCTYPE html>" in html
    assert "<td>1</td>" in html
