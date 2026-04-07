from __future__ import annotations

import json
from pathlib import Path

from Contract_Review_System.word2md.src.word2md.common import SourceItem
from Contract_Review_System.word2md.src.word2md.pipeline import process_one


def test_process_one_uses_local_pdf_parser_without_docling(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%mock\n")

    def _unexpected_docling(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("PDF 路径不应再调用 Docling。")

    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.run_docling",
        _unexpected_docling,
    )
    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.build_fallback_markdown",
        lambda *_args, **_kwargs: (
            "# demo\n\n## 第 1 页\n\nhello contract\n",
            {"page_count": 1, "non_empty_page_count": 1, "line_count": 1, "used_pypdf": True},
        ),
    )

    item = SourceItem(
        sample_id="demo-pdf",
        source_path=pdf_path,
        file_type="pdf",
        output_subdir=Path("demo-pdf"),
    )
    result = process_one(
        item,
        "demo-run",
        tmp_path / "outputs",
        "cpu",
        False,
        [tmp_path / "outputs"],
    )

    assert result["status"] == "ok"
    markdown_path = Path(str(result["output_md"]))
    assert markdown_path.exists()
    assert "hello contract" in markdown_path.read_text(encoding="utf-8")
    meta = json.loads(markdown_path.with_name("meta.json").read_text(encoding="utf-8"))
    assert meta["fallback_pdf_parse"]["applied"] is True
    assert meta["fallback_pdf_parse"]["parser"] == "pypdf_or_pypdf2"
