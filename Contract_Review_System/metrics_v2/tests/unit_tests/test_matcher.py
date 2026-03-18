from __future__ import annotations

from contract_metrics_v2.matcher import pair_clause_risks
from contract_metrics_v2.types import RiskItem


def test_pair_clause_risks_matches_best_item() -> None:
    gold = [
        RiskItem(
            risk_id="g1",
            contract_id="demo",
            title="主体信息缺失",
            clause_text="甲方信息为空",
            explanation="主体不明确会影响送达",
            suggestion="补充主体信息",
            source_excerpt="",
        )
    ]
    preds = [
        RiskItem(
            risk_id="p1",
            contract_id="demo",
            title="主体信息不完整",
            clause_text="甲方信息为空",
            explanation="主体不明可能影响通知送达",
            suggestion="建议补充主体信息",
            source_excerpt="",
        )
    ]

    pairs, unmatched_gold, unmatched_pred = pair_clause_risks(gold, preds, threshold=0.3)
    assert len(pairs) == 1
    assert not unmatched_gold
    assert not unmatched_pred
