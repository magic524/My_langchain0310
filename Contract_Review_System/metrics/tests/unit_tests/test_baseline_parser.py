from __future__ import annotations

from contract_metrics.baseline_parser import parse_baseline_markdown


def test_final_applied_filters_plain_numbered_clauses(tmp_path) -> None:
    md_path = tmp_path / "final.md"
    md_path.write_text(
        """
# 服务协议

1、服务项目：播放器升级
2、服务地点：坦桑尼亚
3、服务完成时间：2026年03月31日前
""".strip(),
        encoding="utf-8",
    )

    items = parse_baseline_markdown(
        contract_id="demo_contract",
        participant="final_applied",
        markdown_path=md_path,
    )
    assert items == []


def test_final_applied_keeps_inline_risk_comment(tmp_path) -> None:
    md_path = tmp_path / "final_with_comment.md"
    md_path.write_text(
        """
1、服务标准【批注#1/段落20/作者A: 【风险点】服务标准不明确【说明】验收标准缺失可能导致争议【修改建议】补充验收口径】
""".strip(),
        encoding="utf-8",
    )

    items = parse_baseline_markdown(
        contract_id="demo_contract",
        participant="final_applied",
        markdown_path=md_path,
    )
    assert len(items) == 1
    assert "服务标准不明确" in items[0].title
    assert "验收标准缺失" in items[0].explanation
    assert "补充验收口径" in items[0].suggestion


def test_third_party_keeps_structured_entries(tmp_path) -> None:
    md_path = tmp_path / "third_party.md"
    md_path.write_text(
        """
1、主体信息不完整

| **条款原文** | **修改建议** |
|---|---|
| 统一社会信用代码/身份证号： | 补充完整信息 |
| **修改理由** | |
| 主体信息缺失导致履约风险 | 主体信息缺失导致履约风险 |
""".strip(),
        encoding="utf-8",
    )

    items = parse_baseline_markdown(
        contract_id="demo_contract",
        participant="third_party",
        markdown_path=md_path,
    )
    assert len(items) == 1
    assert "主体信息不完整" in items[0].title
    assert "统一社会信用代码" in items[0].clause_text
    assert "履约风险" in items[0].explanation
    assert "补充完整信息" in items[0].suggestion
