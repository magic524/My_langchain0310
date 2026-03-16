from __future__ import annotations

import json

from contract_metrics.label_parser import classify_label_status, parse_label_markdown


def test_classify_label_status() -> None:
    assert classify_label_status("采纳。原因：xxx") == "accept"
    assert classify_label_status("部分采纳 原因：xxx") == "partial"
    assert classify_label_status("未采纳 原因：xxx") == "reject"
    assert classify_label_status("仅备注") == "other"


def test_parse_label_markdown(tmp_path) -> None:
    md_path = tmp_path / "output.md"
    meta_path = tmp_path / "meta.json"

    md_path.write_text(
        """
1、主体信息不完整【批注#1/段落3/作者A: 采纳 原因：需补全主体信息】

| **条款原文** | **修改建议** |
|---|---|
| 统一社会信用代码/身份证号： | 补充完整信息 |
| **修改理由** | |
| 主体信息缺失导致履约风险 | 主体信息缺失导致履约风险 |
""".strip(),
        encoding="utf-8",
    )

    meta_path.write_text(
        json.dumps(
            {
                "comment_anchors": [
                    {
                        "paragraph_excerpt": "1、主体信息不完整",
                        "comment_text": "采纳 原因：需补全主体信息",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    items = parse_label_markdown(
        contract_id="demo",
        adoption_md_path=md_path,
        adoption_meta_path=meta_path,
    )

    assert len(items) == 1
    assert items[0].status == "accept"
    assert "主体信息" in items[0].title
    assert "统一社会信用代码" in items[0].clause_text
    assert "主体信息缺失" in items[0].explanation
    assert "补充完整" in items[0].suggestion
