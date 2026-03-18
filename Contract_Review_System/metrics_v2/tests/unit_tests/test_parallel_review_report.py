from __future__ import annotations

from pathlib import Path

from contract_metrics_v2.parallel_review_report import (
    _aggregate_policy,
    ContractParallelAudit,
    ParticipantPolicyAudit,
    normalize_display_risk,
)
from contract_metrics_v2.types import BinaryMetrics, RiskItem


def test_normalize_display_risk_extracts_embedded_fields() -> None:
    item = RiskItem(
        risk_id="r1",
        contract_id="demo",
        title=(
            "原条款内容【批注#1/段落3/作者Mia: "
            "【风险点】验收标准不明确"
            "【说明】原条款未明确验收口径，容易引发争议。"
            "【修改建议】建议补充验收标准和时限。】"
        ),
        clause_text="",
        explanation="",
        suggestion="",
        source_excerpt="",
    )

    normalized = normalize_display_risk(item)

    assert normalized.title == "验收标准不明确"
    assert normalized.explanation == "原条款未明确验收口径，容易引发争议。"
    assert normalized.suggestion == "建议补充验收标准和时限。"
    assert normalized.clause_text == "原条款内容"


def test_normalize_display_risk_strips_style_tail_noise() -> None:
    item = RiskItem(
        risk_id="r2",
        contract_id="demo",
        title="【风险点】协议目的表述不准确【说明】表述偏差可能引发争议。【修改建议】补充项目实际用途。；样式/段落8: color#999999】 | **修改理由** |",
        clause_text="",
        explanation="",
        suggestion="",
        source_excerpt="",
    )

    normalized = normalize_display_risk(item)

    assert normalized.title == "协议目的表述不准确"
    assert normalized.explanation == "表述偏差可能引发争议。"
    assert normalized.suggestion == "补充项目实际用途。"


def test_aggregate_policy_uses_contract_average_for_text_scores() -> None:
    metrics = BinaryMetrics(precision=0.0, recall=0.0, f1=0.0, tp=0, fp=0, fn=0)
    audits = [
        ContractParallelAudit(
            contract_id=f"demo-{index}",
            output_dir=Path("."),
            source_files={},
            clause_lookup={},
            gold_risks=[],
            local_llm_risks=[],
            third_party_risks=[],
            audits={
                ("third_party", "adopted_only"): ParticipantPolicyAudit(
                    participant="third_party",
                    policy="adopted_only",
                    clause_metrics=metrics,
                    risk_metrics=metrics,
                    matched_pairs=[],
                    unmatched_gold=[],
                    unmatched_prediction=[],
                    explanation_structure_score=score,
                    suggestion_actionability_score=suggestion,
                    gold_risk_count=0,
                    predicted_risk_count=0,
                )
            },
        )
        for index, (score, suggestion) in enumerate(((0.75, 0.25), (1.0, 1.0), (0.0, 0.0)), start=1)
    ]

    aggregate = _aggregate_policy(audits, participant="third_party", policy="adopted_only")

    assert aggregate["explanation_score"] == (0.75 + 1.0 + 0.0) / 3
    assert aggregate["suggestion_score"] == (0.25 + 1.0 + 0.0) / 3
    assert aggregate["contract_count"] == 3
