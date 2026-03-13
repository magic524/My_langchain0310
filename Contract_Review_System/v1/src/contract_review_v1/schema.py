from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ParsedReview:
    """Structured review result for a clause.

    Args:
        has_risk: Whether the output identifies any risk in the clause.
        risk_level: Risk level in Chinese, expected values are high/medium/low labels.
        risk_points: Explicit risk points extracted from output.
        explanation: Explanation text for the detected risk.
        suggestion: Suggested revision text.
        raw_text: Original full output text.
    """

    has_risk: bool
    risk_level: str | None
    risk_points: list[str]
    explanation: str
    suggestion: str
    raw_text: str


@dataclass(slots=True)
class ClauseEvaluationRecord:
    """Evaluation payload for a single clause.

    Args:
        contract_id: Unique contract identifier.
        clause_id: Unique clause identifier.
        clause_text: Original clause text.
        ground_truth: Human-adopted ground truth for comparison.
        third_party: Third-party platform output.
        final_applied: Their final applied version output.
        explanation_keywords: Expected explanation keywords.
        suggestion_keywords: Expected suggestion keywords.
    """

    contract_id: str
    clause_id: str
    clause_text: str
    ground_truth: ParsedReview
    third_party: ParsedReview
    final_applied: ParsedReview
    explanation_keywords: list[str]
    suggestion_keywords: list[str]


def _to_review(payload: dict[str, Any], *, default_raw_text: str = "") -> ParsedReview:
    risk_points = payload.get("risk_points") or []
    if not isinstance(risk_points, list):
        msg = "`risk_points` must be a list"
        raise ValueError(msg)

    return ParsedReview(
        has_risk=bool(payload.get("has_risk", False)),
        risk_level=payload.get("risk_level"),
        risk_points=[str(item).strip() for item in risk_points if str(item).strip()],
        explanation=str(payload.get("explanation", "")).strip(),
        suggestion=str(payload.get("suggestion", "")).strip(),
        raw_text=str(payload.get("raw_text", default_raw_text)).strip(),
    )


def load_dataset(dataset_path: Path) -> list[ClauseEvaluationRecord]:
    """Load dataset JSON and convert it to normalized records.

    Args:
        dataset_path: Path to JSON dataset file.

    Returns:
        Normalized clause-level evaluation records.
    """

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    contracts = payload.get("contracts")
    if not isinstance(contracts, list):
        msg = "Dataset must contain `contracts` as a list"
        raise ValueError(msg)

    records: list[ClauseEvaluationRecord] = []
    for contract in contracts:
        contract_id = str(contract.get("contract_id", "")).strip()
        clauses = contract.get("clauses")
        if not contract_id or not isinstance(clauses, list):
            msg = "Each contract needs `contract_id` and `clauses` list"
            raise ValueError(msg)

        for clause in clauses:
            clause_id = str(clause.get("clause_id", "")).strip()
            clause_text = str(clause.get("clause_text", "")).strip()
            if not clause_id or not clause_text:
                msg = "Each clause needs `clause_id` and `clause_text`"
                raise ValueError(msg)

            ground_truth = _to_review(clause.get("ground_truth", {}))
            third_party = _to_review(clause.get("third_party", {}))
            final_applied = _to_review(clause.get("final_applied", {}))

            explanation_keywords = [
                str(item).strip()
                for item in clause.get("explanation_keywords", [])
                if str(item).strip()
            ]
            suggestion_keywords = [
                str(item).strip()
                for item in clause.get("suggestion_keywords", [])
                if str(item).strip()
            ]

            records.append(
                ClauseEvaluationRecord(
                    contract_id=contract_id,
                    clause_id=clause_id,
                    clause_text=clause_text,
                    ground_truth=ground_truth,
                    third_party=third_party,
                    final_applied=final_applied,
                    explanation_keywords=explanation_keywords,
                    suggestion_keywords=suggestion_keywords,
                )
            )

    return records
