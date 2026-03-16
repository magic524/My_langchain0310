from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ClauseRecord:
    """Single contract clause unit.

    Args:
        clause_id: Unique clause id in a contract.
        clause_text: Clause raw text.
    """

    clause_id: str
    clause_text: str


@dataclass(slots=True)
class RiskEntry:
    """Risk entry extracted from labels/baselines/predictions.

    Args:
        risk_id: Unique risk entry id.
        contract_id: Contract identifier.
        title: Risk title.
        clause_text: Clause quote used for matching.
        explanation: Risk explanation.
        suggestion: Suggested revision.
        source_excerpt: Raw source excerpt for trace.
        status: Label status (`accept`, `partial`, `reject`, `other`) for labels.
        status_reason: Optional status rationale text.
    """

    risk_id: str
    contract_id: str
    title: str
    clause_text: str
    explanation: str
    suggestion: str
    source_excerpt: str
    status: str = "other"
    status_reason: str = ""


@dataclass(slots=True)
class ContractDataset:
    """Dataset payload for one contract.

    Args:
        contract_id: Contract identifier.
        source_files: Source file mapping.
        clauses: Extracted clause units.
        labels: Label risk entries from adoption notes.
        baselines: Baseline risk entries keyed by participant.
    """

    contract_id: str
    source_files: dict[str, str]
    clauses: list[ClauseRecord]
    labels: list[RiskEntry]
    baselines: dict[str, list[RiskEntry]] = field(default_factory=dict)


@dataclass(slots=True)
class DatasetPayload:
    """Built dataset root payload.

    Args:
        meta: Dataset metadata.
        contracts: Contract datasets.
        warnings: Build warnings.
    """

    meta: dict[str, Any]
    contracts: list[ContractDataset]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParticipantPrediction:
    """Prediction entries for one participant and contract.

    Args:
        participant: Participant name.
        contract_id: Contract identifier.
        risks: Parsed risk entries.
    """

    participant: str
    contract_id: str
    risks: list[RiskEntry]


@dataclass(slots=True)
class IdentificationCounts:
    """Binary identification confusion matrix counts."""

    tp: int
    fp: int
    tn: int
    fn: int


@dataclass(slots=True)
class IdentificationMetrics:
    """Risk identification metrics."""

    accuracy: float
    miss_rate: float
    false_positive_rate: float
    counts: IdentificationCounts


@dataclass(slots=True)
class ExplanationMetrics:
    """Risk explanation metrics for true-positive matched clauses."""

    direction_consistency: float
    accuracy: float
    completeness: float
    sample_size: int


@dataclass(slots=True)
class SuggestionMetrics:
    """Risk suggestion metrics for true-positive matched clauses."""

    direction_consistency: float
    content_accuracy: float
    completeness: float
    sample_size: int


@dataclass(slots=True)
class ParticipantPolicyResult:
    """All metrics for one participant under one policy."""

    participant: str
    policy: str
    identification: IdentificationMetrics
    explanation: ExplanationMetrics
    suggestion: SuggestionMetrics


@dataclass(slots=True)
class EvaluationPayload:
    """Evaluation result root payload."""

    meta: dict[str, Any]
    participant_results: list[ParticipantPolicyResult]
    contract_results: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def dataclass_to_dict(item: Any) -> dict[str, Any]:
    """Convert nested dataclasses to dict.

    Args:
        item: Dataclass instance.

    Returns:
        JSON-serializable dictionary.
    """
    return asdict(item)
