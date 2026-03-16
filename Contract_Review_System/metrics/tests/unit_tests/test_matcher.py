from __future__ import annotations

from contract_metrics.matcher import align_risks_to_clauses
from contract_metrics.types import ClauseRecord, RiskEntry


def test_align_risks_to_clauses() -> None:
    clauses = [
        ClauseRecord(clause_id="c1", clause_text="统一社会信用代码/身份证号："),
        ClauseRecord(clause_id="c2", clause_text="争议由甲方所在地法院管辖"),
    ]
    risks = [
        RiskEntry(
            risk_id="r1",
            contract_id="demo",
            title="主体信息缺失",
            clause_text="统一社会信用代码/身份证号",
            explanation="信息缺失导致主体不明",
            suggestion="补充主体信息",
            source_excerpt="...",
        ),
        RiskEntry(
            risk_id="r2",
            contract_id="demo",
            title="无关条款",
            clause_text="完全不匹配",
            explanation="",
            suggestion="",
            source_excerpt="...",
        ),
    ]

    mapped = align_risks_to_clauses(risks, clauses, threshold=0.25)
    assert len(mapped.clause_to_risks["c1"]) == 1
    assert mapped.clause_to_risks["c1"][0].risk_id == "r1"
    assert any(item.risk_id == "r2" for item in mapped.unmatched_risks)
