from __future__ import annotations

from dataclasses import dataclass

from .text_utils import text_similarity
from .types import ClauseRecord, RiskEntry


@dataclass(slots=True)
class ClauseRiskMapping:
    """Risk-to-clause mapping result."""

    clause_to_risks: dict[str, list[RiskEntry]]
    unmatched_risks: list[RiskEntry]


def _match_query(risk: RiskEntry) -> str:
    if risk.clause_text:
        return risk.clause_text
    if risk.explanation:
        return risk.explanation
    return risk.title


def align_risks_to_clauses(
    risks: list[RiskEntry],
    clauses: list[ClauseRecord],
    *,
    threshold: float,
) -> ClauseRiskMapping:
    """Align risk entries to clause units.

    Args:
        risks: Risk entries.
        clauses: Contract clauses.
        threshold: Minimum similarity threshold.

    Returns:
        Mapping object with matched and unmatched entries.
    """
    clause_to_risks: dict[str, list[RiskEntry]] = {clause.clause_id: [] for clause in clauses}
    unmatched: list[RiskEntry] = []

    if not clauses:
        return ClauseRiskMapping(clause_to_risks={}, unmatched_risks=risks)

    for risk in risks:
        query = _match_query(risk)
        best_score = 0.0
        best_clause: ClauseRecord | None = None

        for clause in clauses:
            score = text_similarity(query, clause.clause_text)
            if score > best_score:
                best_score = score
                best_clause = clause

        if best_clause is None or best_score < threshold:
            unmatched.append(risk)
            continue
        clause_to_risks[best_clause.clause_id].append(risk)

    return ClauseRiskMapping(clause_to_risks=clause_to_risks, unmatched_risks=unmatched)
