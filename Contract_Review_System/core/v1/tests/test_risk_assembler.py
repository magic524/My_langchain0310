from __future__ import annotations

from Contract_Review_System.core.v1.src.crsv1.risk_assembler import (
    aggregate_clause_risks,
    build_risk_statistics,
    filter_risks_by_level,
    normalize_display_risk_levels,
)
from Contract_Review_System.core.v1.src.crsv1.runtime_types import ClauseReviewResult, ClauseRisk


def _risk(risk_id: str, title: str, target_text: str) -> ClauseRisk:
    return ClauseRisk(
        risk_id=risk_id,
        contract_id="c1",
        parent_clause_id="p1",
        target_clause_id="n1",
        target_text=target_text,
        risk_title=title,
        risk_level="high",
        risk_type="付款",
        explanation="说明",
        suggestion="建议",
        evidence_source="n1",
    )


def test_aggregate_clause_risks_deduplicates_similar_entries() -> None:
    reviews = [
        ClauseReviewResult(
            task_id="t1",
            contract_id="c1",
            parent_clause_id="p1",
            parent_heading="付款",
            risks=[
                _risk("r1", "付款条件不明确", "甲方收到发票后付款"),
                _risk("r2", "付款条件不明确", "甲方收到发票后付款"),
            ],
        )
    ]
    aggregated = aggregate_clause_risks(reviews)
    assert len(aggregated) == 1
    stats = build_risk_statistics(aggregated)
    assert stats["risk_count"] == 1
    assert stats["by_level"]["high"] == 1


def test_filter_risks_by_level_keeps_only_selected_levels() -> None:
    missing_risk = _risk("r_missing", "主体信息缺失", "甲方：")
    missing_risk.risk_level = "missing"
    low_risk = _risk("r_low", "表述可优化", "通知地址")
    low_risk.risk_level = "low"
    risks = [missing_risk, _risk("r_high", "违约责任失衡", "违约责任"), low_risk]

    filtered = filter_risks_by_level(risks, ["missing", "high"])

    assert [risk.risk_level for risk in filtered] == ["missing", "high"]


def test_normalize_display_risk_levels_supports_chinese_labels() -> None:
    assert normalize_display_risk_levels(["信息缺失风险", "高风险", "低风险"]) == ["missing", "high", "low"]
