from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .judge import (
    JudgeThresholds,
    LLMRuntimeConfig,
    llm_explanation_scores,
    llm_suggestion_scores,
    rule_explanation_scores,
    rule_suggestion_scores,
)
from .text_utils import text_similarity
from .types import (
    ClauseRecord,
    ExplanationMetrics,
    IdentificationCounts,
    IdentificationMetrics,
    ParticipantPolicyResult,
    RiskEntry,
    SuggestionMetrics,
)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _positive_label_entries(policy: str, labels: list[RiskEntry]) -> list[RiskEntry]:
    if policy == "policy_a":
        return [entry for entry in labels if entry.status in {"accept", "partial"}]
    return list(labels)


def _reference_label(policy: str, labels: list[RiskEntry]) -> RiskEntry | None:
    positives = _positive_label_entries(policy, labels)
    if not positives:
        return None
    # Prefer accepted entries for policy A.
    order = {"accept": 0, "partial": 1, "reject": 2, "other": 3}
    ranked = sorted(positives, key=lambda item: order.get(item.status, 4))
    return ranked[0]


def _pick_prediction(reference: RiskEntry, predictions: list[RiskEntry]) -> RiskEntry:
    if not predictions:
        return RiskEntry(
            risk_id="empty",
            contract_id=reference.contract_id,
            title="",
            clause_text="",
            explanation="",
            suggestion="",
            source_excerpt="",
        )

    best = predictions[0]
    best_score = 0.0
    for prediction in predictions:
        score = max(
            text_similarity(prediction.title, reference.title),
            text_similarity(prediction.explanation, reference.explanation),
            text_similarity(prediction.suggestion, reference.suggestion),
        )
        if score > best_score:
            best = prediction
            best_score = score
    return best


def _aggregate(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def evaluate_clause_level(
    *,
    policy: str,
    clauses: list[ClauseRecord],
    labels_by_clause: dict[str, list[RiskEntry]],
    predictions_by_clause: dict[str, list[RiskEntry]],
    thresholds: JudgeThresholds,
    use_llm_judge: bool,
    llm_runtime: LLMRuntimeConfig | None,
) -> tuple[IdentificationMetrics, ExplanationMetrics, SuggestionMetrics, dict[str, Any]]:
    """Evaluate participant metrics for one contract.

    Args:
        policy: `policy_a` or `policy_b`.
        clauses: Clause records.
        labels_by_clause: Label mapping.
        predictions_by_clause: Prediction mapping.
        thresholds: Judge thresholds.
        use_llm_judge: Whether to use LLM judge.
        llm_runtime: Optional LLM runtime.

    Returns:
        Tuple of identification/explanation/suggestion metrics and detail dict.
    """
    tp = fp = tn = fn = 0
    tp_pairs: list[tuple[RiskEntry, RiskEntry]] = []

    clause_details: list[dict[str, Any]] = []

    for clause in clauses:
        label_entries = labels_by_clause.get(clause.clause_id, [])
        prediction_entries = predictions_by_clause.get(clause.clause_id, [])

        label_positive = bool(_positive_label_entries(policy, label_entries))
        predicted_positive = bool(prediction_entries)

        if label_positive and predicted_positive:
            tp += 1
            reference = _reference_label(policy, label_entries)
            if reference is not None:
                prediction = _pick_prediction(reference, prediction_entries)
                tp_pairs.append((reference, prediction))
        elif label_positive and not predicted_positive:
            fn += 1
        elif (not label_positive) and predicted_positive:
            fp += 1
        else:
            tn += 1

        clause_details.append(
            {
                "clause_id": clause.clause_id,
                "clause_text": clause.clause_text,
                "label_positive": label_positive,
                "predicted_positive": predicted_positive,
                "label_count": len(label_entries),
                "prediction_count": len(prediction_entries),
            }
        )

    counts = IdentificationCounts(tp=tp, fp=fp, tn=tn, fn=fn)
    identification = IdentificationMetrics(
        accuracy=_safe_div(tp + tn, tp + tn + fp + fn),
        miss_rate=_safe_div(fn, tp + fn),
        false_positive_rate=_safe_div(fp, fp + tn),
        counts=counts,
    )

    exp_direction_values: list[float] = []
    exp_accuracy_values: list[float] = []
    exp_complete_values: list[float] = []

    sug_direction_values: list[float] = []
    sug_accuracy_values: list[float] = []
    sug_complete_values: list[float] = []

    scored_pairs: list[dict[str, Any]] = []
    for label, prediction in tp_pairs:
        if use_llm_judge and llm_runtime is not None:
            explanation_scores = llm_explanation_scores(llm_runtime, label=label, prediction=prediction)
            suggestion_scores = llm_suggestion_scores(llm_runtime, label=label, prediction=prediction)
        else:
            explanation_scores = rule_explanation_scores(
                label=label,
                prediction=prediction,
                thresholds=thresholds,
            )
            suggestion_scores = rule_suggestion_scores(
                label=label,
                prediction=prediction,
                thresholds=thresholds,
            )

        exp_direction_values.append(explanation_scores["direction_consistency"])
        exp_accuracy_values.append(explanation_scores["accuracy"])
        exp_complete_values.append(explanation_scores["completeness"])

        sug_direction_values.append(suggestion_scores["direction_consistency"])
        sug_accuracy_values.append(suggestion_scores["content_accuracy"])
        sug_complete_values.append(suggestion_scores["completeness"])

        scored_pairs.append(
            {
                "label": asdict(label),
                "prediction": asdict(prediction),
                "explanation_scores": explanation_scores,
                "suggestion_scores": suggestion_scores,
            }
        )

    explanation = ExplanationMetrics(
        direction_consistency=_aggregate(exp_direction_values),
        accuracy=_aggregate(exp_accuracy_values),
        completeness=_aggregate(exp_complete_values),
        sample_size=len(tp_pairs),
    )
    suggestion = SuggestionMetrics(
        direction_consistency=_aggregate(sug_direction_values),
        content_accuracy=_aggregate(sug_accuracy_values),
        completeness=_aggregate(sug_complete_values),
        sample_size=len(tp_pairs),
    )

    detail = {
        "clause_details": clause_details,
        "tp_scored_pairs": scored_pairs,
    }
    return identification, explanation, suggestion, detail


def build_policy_result(
    *,
    participant: str,
    policy: str,
    identification: IdentificationMetrics,
    explanation: ExplanationMetrics,
    suggestion: SuggestionMetrics,
) -> ParticipantPolicyResult:
    """Build participant policy result dataclass."""
    return ParticipantPolicyResult(
        participant=participant,
        policy=policy,
        identification=identification,
        explanation=explanation,
        suggestion=suggestion,
    )
