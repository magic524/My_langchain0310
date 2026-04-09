from __future__ import annotations

from .runtime_types import ClauseReviewResult, ClauseRisk
from .text_utils import text_similarity


def aggregate_clause_risks(clause_reviews: list[ClauseReviewResult]) -> list[ClauseRisk]:
    """Aggregate and deduplicate clause risks across parent tasks."""

    aggregated: list[ClauseRisk] = []
    for review in clause_reviews:
        for risk in review.risks:
            duplicate = None
            for existing in aggregated:
                same_target = existing.target_clause_id == risk.target_clause_id
                title_similar = text_similarity(existing.risk_title, risk.risk_title) >= 0.88
                text_similar = text_similarity(existing.target_text, risk.target_text) >= 0.92
                if same_target and (title_similar or text_similar):
                    duplicate = existing
                    break
            if duplicate is not None:
                if len(risk.explanation) > len(duplicate.explanation):
                    duplicate.explanation = risk.explanation
                if len(risk.suggestion) > len(duplicate.suggestion):
                    duplicate.suggestion = risk.suggestion
                continue
            aggregated.append(risk)
    return aggregated


def build_risk_statistics(aggregated_risks: list[ClauseRisk]) -> dict:
    """Build high-level statistics for reports and tables."""

    by_level: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_parent_clause: dict[str, int] = {}
    for risk in aggregated_risks:
        by_level[risk.risk_level] = by_level.get(risk.risk_level, 0) + 1
        by_type[risk.risk_type] = by_type.get(risk.risk_type, 0) + 1
        by_parent_clause[risk.parent_clause_id] = by_parent_clause.get(risk.parent_clause_id, 0) + 1

    return {
        "risk_count": len(aggregated_risks),
        "by_level": dict(sorted(by_level.items())),
        "by_type": dict(sorted(by_type.items())),
        "by_parent_clause": dict(sorted(by_parent_clause.items())),
    }
