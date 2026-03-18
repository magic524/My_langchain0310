from __future__ import annotations

from contract_metrics_v2.clause_parser import extract_clause_units


def test_extract_clause_units_builds_context() -> None:
    markdown = """
# 服务协议

**一、服务范围**

1、服务项目：播放器升级

2、服务地点：坦桑尼亚

**二、违约责任**

1、若乙方未按时完成，应承担责任。
""".strip()

    clauses = extract_clause_units("demo", markdown)

    assert len(clauses) == 3
    assert clauses[0].section_title == "一、服务范围"
    assert "当前条款" in clauses[0].context_text
    assert clauses[1].prev_clause_preview
