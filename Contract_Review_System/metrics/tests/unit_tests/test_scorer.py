from __future__ import annotations

from contract_metrics.judge import JudgeThresholds
from contract_metrics.scorer import evaluate_clause_level
from contract_metrics.types import ClauseRecord, RiskEntry


def test_evaluate_clause_level_basic() -> None:
    clauses = [
        ClauseRecord(clause_id="c1", clause_text="统一社会信用代码/身份证号："),
        ClauseRecord(clause_id="c2", clause_text="争议由甲方所在地法院管辖"),
    ]

    labels_by_clause = {
        "c1": [
            RiskEntry(
                risk_id="l1",
                contract_id="demo",
                title="主体信息不完整",
                clause_text="统一社会信用代码/身份证号：",
                explanation="主体信息缺失导致主体不明，可能影响送达与诉讼。",
                suggestion="补充统一社会信用代码并核验营业执照。",
                source_excerpt="...",
                status="accept",
            )
        ],
        "c2": [],
    }
    predictions_by_clause = {
        "c1": [
            RiskEntry(
                risk_id="p1",
                contract_id="demo",
                title="主体信息缺失",
                clause_text="统一社会信用代码/身份证号：",
                explanation="该字段缺失会导致主体不明，可能引发诉讼送达风险。",
                suggestion="建议补充统一社会信用代码。",
                source_excerpt="...",
            )
        ],
        "c2": [],
    }

    identification, explanation, suggestion, detail = evaluate_clause_level(
        policy="policy_a",
        clauses=clauses,
        labels_by_clause=labels_by_clause,
        predictions_by_clause=predictions_by_clause,
        thresholds=JudgeThresholds(
            direction_consistency_threshold=0.35,
            explanation_accuracy_threshold=0.55,
            suggestion_accuracy_threshold=0.55,
        ),
        use_llm_judge=False,
        llm_runtime=None,
    )

    assert identification.counts.tp == 1
    assert identification.counts.fp == 0
    assert identification.counts.fn == 0
    assert explanation.sample_size == 1
    assert suggestion.sample_size == 1
    assert detail["tp_scored_pairs"]
