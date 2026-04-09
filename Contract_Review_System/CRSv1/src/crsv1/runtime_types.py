from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ReviewPromptContext:
    """Prompt preferences for one CRSv1 run."""

    review_stance: str = ""
    extra_user_instruction: str = ""


@dataclass(slots=True)
class ContractBackgroundBrief:
    """Whole-contract background summary for downstream clause review."""

    contract_type: str = ""
    transaction_purpose: str = ""
    parties_summary: str = ""
    performance_path: list[str] = field(default_factory=list)
    high_risk_topics: list[str] = field(default_factory=list)
    review_focus: list[str] = field(default_factory=list)
    search_hints: list[str] = field(default_factory=list)
    raw_response_excerpt: str = ""


@dataclass(slots=True)
class ClauseNode:
    """One node in the contract clause tree."""

    node_id: str
    contract_id: str
    level: int
    heading: str
    heading_type: str
    parent_id: str
    line_start: int
    line_end: int
    body_lines: list[str] = field(default_factory=list)
    full_text: str = ""
    children: list["ClauseNode"] = field(default_factory=list)


@dataclass(slots=True)
class ClauseReviewTask:
    """A review task centered on one parent clause."""

    task_id: str
    contract_id: str
    parent_clause_id: str
    parent_heading: str
    prompt_text: str
    child_clause_ids: list[str] = field(default_factory=list)
    child_clause_headings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClauseRisk:
    """Structured risk output for CRSv1."""

    risk_id: str
    contract_id: str
    parent_clause_id: str
    target_clause_id: str
    target_text: str
    risk_title: str
    risk_level: str
    risk_type: str
    explanation: str
    suggestion: str
    evidence_source: str
    source_excerpt: str = ""
    match_score: float = 0.0
    anchor_strategy: str = ""


@dataclass(slots=True)
class ClauseReviewResult:
    """Review result for one parent clause task."""

    task_id: str
    contract_id: str
    parent_clause_id: str
    parent_heading: str
    raw_response_path: str = ""
    raw_response_excerpt: str = ""
    risks: list[ClauseRisk] = field(default_factory=list)
    warning: str = ""


@dataclass(slots=True)
class ContractReviewResult:
    """CRSv1 single-contract output."""

    contract_id: str
    source_files: dict[str, str]
    review_context: ReviewPromptContext
    background_brief: ContractBackgroundBrief
    clause_tree: list[ClauseNode]
    clause_reviews: list[ClauseReviewResult]
    aggregated_risks: list[ClauseRisk]
    risk_statistics: dict[str, Any]
    report_summary: dict[str, Any]


@dataclass(slots=True)
class ContractInputBundle:
    """Minimal normalized contract input loaded from word2md output."""

    contract_id: str
    source_files: dict[str, str]
    markdown_text: str
    meta: dict[str, Any]


@dataclass(slots=True)
class CRSv1ResultPayload:
    """Top-level CRSv1 result payload."""

    meta: dict[str, Any]
    warnings: list[str]
    contracts: list[ContractReviewResult]
