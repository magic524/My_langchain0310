from __future__ import annotations

import json
from pathlib import Path

from Contract_Review_System.word2md.src.word2md.common import SourceItem
from Contract_Review_System.word2md.src.word2md.pipeline import process_one


def test_process_one_converts_pdf_to_docx_before_docling(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%mock\n")
    converted_docx = tmp_path / "converted" / "demo.docx"
    converted_docx.parent.mkdir(parents=True, exist_ok=True)
    converted_docx.write_bytes(b"PK\x03\x04")

    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.convert_pdf_to_docx",
        lambda *_args, **_kwargs: (converted_docx, "pdf2docx"),
    )
    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.extract_docx_comments_with_anchors",
        lambda _path: [],
    )
    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.extract_docx_style_hints",
        lambda _path: [],
    )
    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.extract_docx_visible_paragraphs",
        lambda _path: [],
    )
    def _fake_export_markdown(_path: Path, output_dir: Path, **_kwargs: object) -> tuple[str, str]:
        (output_dir / "output.md").write_text("# demo\n\nhello contract\n", encoding="utf-8")
        return "ok", ""

    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.export_markdown_from_mammoth",
        _fake_export_markdown,
    )
    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.inject_inline_annotations",
        lambda markdown, _comment_anchors, _style_hints: (markdown, {"comment_matched": 0, "comment_unmatched": 0, "style_matched": 0, "style_unmatched": 0}),
    )
    monkeypatch.setattr(
        "Contract_Review_System.word2md.src.word2md.pipeline.repair_missing_numbered_paragraphs",
        lambda markdown, _paragraphs: (markdown, {}),
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
    assert meta["doc_conversion"]["method"] == "pdf2docx"
    assert meta["doc_conversion"]["output_path"] == str(converted_docx)
    assert meta["markdown_backend_used"] == "mammoth"
