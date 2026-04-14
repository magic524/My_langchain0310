from __future__ import annotations

from .runtime_types import ClauseReviewResult, ClauseRisk
from .text_utils import text_similarity


def normalize_display_risk_levels(levels: list[str] | None) -> list[str]:
    """Normalize requested display risk levels while preserving order."""

    if not levels:
        return ["missing", "high", "low"]

    aliases = {
        "missing": "missing",
        "缺失": "missing",
        "信息缺失风险": "missing",
        "high": "high",
        "高": "high",
        "高风险": "high",
        "low": "low",
        "低": "low",
        "低风险": "low",
    }
    normalized: list[str] = []
    for item in levels:
        mapped = aliases.get(str(item).strip().lower()) or aliases.get(str(item).strip())
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    return normalized or ["missing", "high", "low"]


def filter_risks_by_level(aggregated_risks: list[ClauseRisk], display_levels: list[str] | None) -> list[ClauseRisk]:
    """Filter risks by selected display levels."""

    allowed = set(normalize_display_risk_levels(display_levels))
    return [risk for risk in aggregated_risks if risk.risk_level in allowed]


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
                if risk.risk_level == "missing" and duplicate.risk_level != "missing":
                    duplicate.risk_level = "missing"
                elif risk.risk_level == "high" and duplicate.risk_level == "low":
                    duplicate.risk_level = "high"
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
