from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ReviewPromptContext:
    """单次 CRSv1 运行的提示词上下文配置。"""

    review_stance: str = ""
    extra_user_instruction: str = ""
    display_risk_levels: list[str] = field(default_factory=lambda: ["missing", "high", "low"])


@dataclass(slots=True)
class ContractBackgroundBrief:
    """合同全局背景摘要，供后续分条款审查复用。"""

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
    """合同条款树中的一个节点。"""

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
    """以一个父条款为中心构建的审查任务。"""

    task_id: str
    contract_id: str
    parent_clause_id: str
    parent_heading: str
    prompt_text: str
    child_clause_ids: list[str] = field(default_factory=list)
    child_clause_headings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClauseRisk:
    """CRSv1 输出的结构化风险项。"""

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
    """单个父条款任务的审查结果。"""

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
    """CRSv1 对单份合同的完整输出结果。"""

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
    """从 word2md 输出加载并标准化后的合同输入。"""

    contract_id: str
    source_files: dict[str, str]
    markdown_text: str
    meta: dict[str, Any]


@dataclass(slots=True)
class CRSv1ResultPayload:
    """CRSv1 批量运行的顶层结果载荷。"""

    meta: dict[str, Any]
    warnings: list[str]
    contracts: list[ContractReviewResult]
