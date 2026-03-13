from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .schema import ClauseEvaluationRecord, ParsedReview


@dataclass(slots=True)
class MetricExample:
    """Single example used in markdown report."""

    contract_id: str
    clause_id: str
    clause_text: str
    predicted_text: str
    reference_text: str
    reason: str


@dataclass(slots=True)
class DimensionResult:
    """Metric result with a score and examples."""

    score: float
    correct_example: MetricExample | None
    wrong_example: MetricExample | None


@dataclass(slots=True)
class ParticipantMetrics:
    """All dimensions for one participant."""

    name: str
    risk_accuracy: float
    risk_miss_rate: float
    risk_false_positive_rate: float
    explanation_accuracy: DimensionResult
    suggestion_accuracy: DimensionResult


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _contains_keyword(text: str, keyword: str) -> bool:
    compact_text = re.sub(r"\s+", "", text.lower())
    compact_keyword = re.sub(r"\s+", "", keyword.lower())
    return compact_keyword in compact_text


def _keyword_coverage(text: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 0.0
    hits = sum(1 for keyword in expected_keywords if _contains_keyword(text, keyword))
    return _safe_div(hits, len(expected_keywords))


def _actionability_score(text: str) -> float:
    markers = ("建议", "应", "修改", "补充", "删除", "明确", "替换")
    return 1.0 if any(marker in text for marker in markers) else 0.0


def _explanation_score(record: ClauseEvaluationRecord, prediction: ParsedReview) -> float:
    if not record.ground_truth.has_risk:
        return 1.0 if not prediction.has_risk else 0.0

    expected = record.explanation_keywords or record.ground_truth.risk_points
    return _keyword_coverage(prediction.explanation, expected)


def _suggestion_score(record: ClauseEvaluationRecord, prediction: ParsedReview) -> float:
    if not record.ground_truth.has_risk:
        return 1.0 if not prediction.has_risk else 0.0

    coverage = _keyword_coverage(prediction.suggestion, record.suggestion_keywords)
    actionability = _actionability_score(prediction.suggestion)
    return 0.7 * coverage + 0.3 * actionability


def _pick_examples(
    records: list[ClauseEvaluationRecord],
    predictions: list[ParsedReview],
    scorer: Callable[[ClauseEvaluationRecord, ParsedReview], float],
    *,
    correct_threshold: float,
) -> tuple[MetricExample | None, MetricExample | None, float]:
    values: list[float] = []
    correct_example: MetricExample | None = None
    wrong_example: MetricExample | None = None

    for record, prediction in zip(records, predictions):
        score = scorer(record, prediction)
        values.append(score)

        if score >= correct_threshold and correct_example is None:
            correct_example = MetricExample(
                contract_id=record.contract_id,
                clause_id=record.clause_id,
                clause_text=record.clause_text,
                predicted_text=prediction.raw_text,
                reference_text=record.ground_truth.raw_text,
                reason=f"得分 {score:.2f}，达到正确阈值 {correct_threshold:.2f}",
            )

        if score < correct_threshold and wrong_example is None:
            wrong_example = MetricExample(
                contract_id=record.contract_id,
                clause_id=record.clause_id,
                clause_text=record.clause_text,
                predicted_text=prediction.raw_text,
                reference_text=record.ground_truth.raw_text,
                reason=f"得分 {score:.2f}，低于正确阈值 {correct_threshold:.2f}",
            )

    average_score = _safe_div(sum(values), len(values))
    return correct_example, wrong_example, average_score


def evaluate_participant(
    participant_name: str,
    records: list[ClauseEvaluationRecord],
    predictions: list[ParsedReview],
) -> ParticipantMetrics:
    """Evaluate one participant against human ground truth.

    Args:
        participant_name: Display name in the report.
        records: Ground-truth records.
        predictions: Predictions aligned with records.

    Returns:
        Aggregated metrics and examples for the participant.
    """

    if len(records) != len(predictions):
        msg = "Records and predictions must have the same length"
        raise ValueError(msg)

    tp = fp = tn = fn = 0
    for record, prediction in zip(records, predictions):
        gt = record.ground_truth.has_risk
        pd = prediction.has_risk
        if gt and pd:
            tp += 1
        elif gt and not pd:
            fn += 1
        elif not gt and pd:
            fp += 1
        else:
            tn += 1

    risk_accuracy = _safe_div(tp + tn, tp + tn + fp + fn)
    risk_miss_rate = _safe_div(fn, tp + fn)
    risk_false_positive_rate = _safe_div(fp, fp + tn)

    exp_correct, exp_wrong, exp_score = _pick_examples(
        records,
        predictions,
        _explanation_score,
        correct_threshold=0.8,
    )
    sug_correct, sug_wrong, sug_score = _pick_examples(
        records,
        predictions,
        _suggestion_score,
        correct_threshold=0.75,
    )

    return ParticipantMetrics(
        name=participant_name,
        risk_accuracy=risk_accuracy,
        risk_miss_rate=risk_miss_rate,
        risk_false_positive_rate=risk_false_positive_rate,
        explanation_accuracy=DimensionResult(
            score=exp_score,
            correct_example=exp_correct,
            wrong_example=exp_wrong,
        ),
        suggestion_accuracy=DimensionResult(
            score=sug_score,
            correct_example=sug_correct,
            wrong_example=sug_wrong,
        ),
    )
