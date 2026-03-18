from __future__ import annotations

from contract_metrics_v2.evaluator import _suggestion_actionability_score
from contract_metrics_v2.types import RiskItem


def test_empty_suggestion_is_not_high_score() -> None:
    item = RiskItem(
        risk_id="p1",
        contract_id="demo",
        title="主体信息缺失",
        clause_text="甲方信息为空",
        explanation="主体不明可能导致争议",
        suggestion="无",
        source_excerpt="",
    )
    assert _suggestion_actionability_score(item) == 0.25
