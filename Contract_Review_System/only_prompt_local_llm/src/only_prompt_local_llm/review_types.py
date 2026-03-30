from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ClauseUnit:
    """带上下文的条款块。"""

    clause_id: str
    contract_id: str
    section_title: str
    clause_title: str
    clause_text: str
    prev_clause_preview: str
    next_clause_preview: str
    context_text: str


@dataclass(slots=True)
class RiskItem:
    """风险点结构。"""

    risk_id: str
    contract_id: str
    title: str
    clause_text: str
    explanation: str
    suggestion: str
    source_excerpt: str
    status: str = "other"
    status_reason: str = ""
    clause_id: str = ""
    match_score: float = 0.0


@dataclass(slots=True)
class ContractDataset:
    """单个合同的数据集对象。"""

    contract_id: str
    source_files: dict[str, str]
    full_contract_text: str
    clauses: list[ClauseUnit]
    labels: list[RiskItem]
    participants: dict[str, list[RiskItem]]


@dataclass(slots=True)
class DatasetPayload:
    """数据集总对象。"""

    meta: dict[str, Any]
    warnings: list[str]
    contracts: list[ContractDataset]


@dataclass(slots=True)
class BinaryMetrics:
    """通用二分类指标。"""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


@dataclass(slots=True)
class ParticipantPolicyMetrics:
    """单个参与方、单个口径的指标结果。"""

    participant: str
    policy: str
    clause_metrics: BinaryMetrics
    risk_metrics: BinaryMetrics
    explanation_structure_score: float
    suggestion_actionability_score: float
    exact_title_overlap: float
    exact_suggestion_overlap: float
    matched_pairs: int
    gold_risk_count: int
    predicted_risk_count: int


@dataclass(slots=True)
class EvaluationPayload:
    """评估结果总对象。"""

    meta: dict[str, Any]
    warnings: list[str]
    participant_results: list[ParticipantPolicyMetrics]
    contract_results: list[dict[str, Any]] = field(default_factory=list)

