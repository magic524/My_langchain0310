from __future__ import annotations

from dataclasses import replace

from .text_utils import text_similarity
from .types import ClauseUnit, RiskItem


def align_risks_to_clauses(
    risks: list[RiskItem],
    clauses: list[ClauseUnit],
    *,
    threshold: float,
) -> tuple[dict[str, list[RiskItem]], list[RiskItem]]:
    """把风险点对齐到最相近的条款。"""

    mapping: dict[str, list[RiskItem]] = {clause.clause_id: [] for clause in clauses}
    unmatched: list[RiskItem] = []

    if not clauses:
        return {}, list(risks)

    for risk in risks:
        query = risk.clause_text or risk.explanation or risk.title
        best_clause: ClauseUnit | None = None
        best_score = 0.0

        for clause in clauses:
            score = text_similarity(query, clause.clause_text)
            if score > best_score:
                best_score = score
                best_clause = clause

        if best_clause is None or best_score < threshold:
            unmatched.append(risk)
            continue

        mapping[best_clause.clause_id].append(
            replace(risk, clause_id=best_clause.clause_id, match_score=best_score)
        )
    return mapping, unmatched


def pair_clause_risks(
    gold_risks: list[RiskItem],
    pred_risks: list[RiskItem],
    *,
    threshold: float,
) -> tuple[list[tuple[RiskItem, RiskItem, float]], list[RiskItem], list[RiskItem]]:
    """在同一条款内做风险点一对一匹配。"""

    pairs: list[tuple[RiskItem, RiskItem, float]] = []
    remaining_preds = pred_risks[:]
    unmatched_gold: list[RiskItem] = []

    for gold in gold_risks:
        best_index = -1
        best_score = 0.0
        for index, pred in enumerate(remaining_preds):
            score = max(
                text_similarity(gold.title, pred.title),
                text_similarity(gold.explanation, pred.explanation),
                text_similarity(gold.suggestion, pred.suggestion),
                text_similarity(gold.clause_text, pred.clause_text),
            )
            if score > best_score:
                best_score = score
                best_index = index

        if best_index == -1 or best_score < threshold:
            unmatched_gold.append(gold)
            continue

        pred = remaining_preds.pop(best_index)
        pairs.append((gold, pred, best_score))

    unmatched_pred = remaining_preds
    return pairs, unmatched_gold, unmatched_pred
