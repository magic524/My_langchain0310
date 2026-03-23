from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .matcher import align_risks_to_clauses, pair_clause_risks
from .text_utils import contains_any, normalize_text
from .types import (
    BinaryMetrics,
    ClauseUnit,
    ContractDataset,
    EvaluationPayload,
    ParticipantPolicyMetrics,
    RiskItem,
)


def _binary_metrics(tp: int, fp: int, fn: int) -> BinaryMetrics:
    """统一计算 precision / recall / f1。"""

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return BinaryMetrics(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn)


def _parse_clause(item: dict[str, Any]) -> ClauseUnit:
    return ClauseUnit(**item)


def _parse_risk(item: dict[str, Any]) -> RiskItem:
    return RiskItem(**item)


def _parse_contract(item: dict[str, Any]) -> ContractDataset:
    return ContractDataset(
        contract_id=str(item.get("contract_id", "")),
        source_files={str(key): str(value) for key, value in (item.get("source_files") or {}).items()},
        full_contract_text=str(item.get("full_contract_text", "")),
        clauses=[_parse_clause(value) for value in item.get("clauses", [])],
        labels=[_parse_risk(value) for value in item.get("labels", [])],
        participants={
            str(key): [_parse_risk(value) for value in values]
            for key, values in (item.get("participants") or {}).items()
        },
    )


def load_dataset(dataset_path: Path) -> tuple[dict[str, Any], list[str], list[ContractDataset]]:
    """加载数据集。"""

    payload = read_json(dataset_path)
    contracts = [_parse_contract(item) for item in payload.get("contracts", []) if isinstance(item, dict)]
    warnings = [str(item) for item in payload.get("warnings", [])]
    meta = payload.get("meta") or {}
    return meta, warnings, contracts


def _policy_gold_risks(policy: str, labels: list[RiskItem]) -> list[RiskItem]:
    """根据口径选择 gold 风险点。"""

    if policy == "adopted_only":
        return [item for item in labels if item.status in {"accept", "partial"}]
    return list(labels)


def _clause_metrics(
    gold_map: dict[str, list[RiskItem]],
    pred_map: dict[str, list[RiskItem]],
    clauses: list[ClauseUnit],
) -> BinaryMetrics:
    """计算条款层指标。"""

    tp = fp = fn = 0
    for clause in clauses:
        gold_positive = bool(gold_map.get(clause.clause_id, []))
        pred_positive = bool(pred_map.get(clause.clause_id, []))
        if gold_positive and pred_positive:
            tp += 1
        elif gold_positive and not pred_positive:
            fn += 1
        elif (not gold_positive) and pred_positive:
            fp += 1
    return _binary_metrics(tp, fp, fn)


def _explanation_structure_score(gold: RiskItem, pred: RiskItem) -> float:
    """解释结构分，避免直接把文本相同当作高分。"""

    title_ok = 1.0 if pred.title and pred.title != "无" else 0.0
    reason_ok = 1.0 if pred.explanation and len(normalize_text(pred.explanation)) >= 12 else 0.0
    consequence_ok = 1.0 if contains_any(pred.explanation, ("导致", "可能", "损失", "责任", "争议", "后果", "风险")) else 0.0
    clause_bind_ok = 1.0 if pred.clause_text or gold.clause_text else 0.0
    return (title_ok + reason_ok + consequence_ok + clause_bind_ok) / 4.0


def _suggestion_actionability_score(pred: RiskItem) -> float:
    """建议可执行分，空建议不再算高分。"""

    nonempty = 1.0 if pred.suggestion and pred.suggestion != "无" else 0.0
    actionable = (
        1.0
        if contains_any(pred.suggestion, ("建议", "应", "应当", "修改", "补充", "删除", "明确", "增加", "调整"))
        else 0.0
    )
    clause_bind = 1.0 if pred.clause_text else 0.0
    concrete = 1.0 if len(normalize_text(pred.suggestion)) >= 16 and pred.suggestion != "无" else 0.0
    return (nonempty + actionable + clause_bind + concrete) / 4.0


def _exact_overlap_rate(values: list[tuple[str, str]]) -> float:
    """计算精确重合率。"""

    if not values:
        return 0.0
    exact = sum(1 for left, right in values if normalize_text(left) and normalize_text(left) == normalize_text(right))
    return exact / len(values)


def evaluate_contract(
    contract: ContractDataset,
    *,
    participant: str,
    policy: str,
    clause_match_threshold: float,
    risk_match_threshold: float,
) -> tuple[ParticipantPolicyMetrics, dict[str, Any], list[str]]:
    """评估单个合同。"""

    warnings: list[str] = []
    gold_risks = _policy_gold_risks(policy, contract.labels)
    gold_map, unmatched_gold_align = align_risks_to_clauses(gold_risks, contract.clauses, threshold=clause_match_threshold)
    pred_map, unmatched_pred_align = align_risks_to_clauses(
        contract.participants.get(participant, []),
        contract.clauses,
        threshold=clause_match_threshold,
    )

    if unmatched_gold_align:
        warnings.append(f"{contract.contract_id}: {len(unmatched_gold_align)} gold risks unmatched")
    if unmatched_pred_align:
        warnings.append(f"{contract.contract_id}/{participant}: {len(unmatched_pred_align)} predicted risks unmatched")

    clause_metrics = _clause_metrics(gold_map, pred_map, contract.clauses)

    matched_pairs: list[tuple[RiskItem, RiskItem, float]] = []
    unmatched_gold: list[RiskItem] = []
    unmatched_pred: list[RiskItem] = []
    for clause in contract.clauses:
        clause_pairs, clause_unmatched_gold, clause_unmatched_pred = pair_clause_risks(
            gold_map.get(clause.clause_id, []),
            pred_map.get(clause.clause_id, []),
            threshold=risk_match_threshold,
        )
        matched_pairs.extend(clause_pairs)
        unmatched_gold.extend(clause_unmatched_gold)
        unmatched_pred.extend(clause_unmatched_pred)

    risk_metrics = _binary_metrics(len(matched_pairs), len(unmatched_pred), len(unmatched_gold))
    explanation_score = (
        sum(_explanation_structure_score(gold, pred) for gold, pred, _ in matched_pairs) / len(matched_pairs)
        if matched_pairs
        else 0.0
    )
    suggestion_score = (
        sum(_suggestion_actionability_score(pred) for _, pred, _ in matched_pairs) / len(matched_pairs)
        if matched_pairs
        else 0.0
    )
    title_overlap = _exact_overlap_rate([(gold.title, pred.title) for gold, pred, _ in matched_pairs])

    suggestion_pairs = [
        (gold.suggestion, pred.suggestion)
        for gold, pred, _ in matched_pairs
        if normalize_text(gold.suggestion) and normalize_text(pred.suggestion)
    ]
    suggestion_overlap = _exact_overlap_rate(suggestion_pairs)

    metrics = ParticipantPolicyMetrics(
        participant=participant,
        policy=policy,
        clause_metrics=clause_metrics,
        risk_metrics=risk_metrics,
        explanation_structure_score=explanation_score,
        suggestion_actionability_score=suggestion_score,
        exact_title_overlap=title_overlap,
        exact_suggestion_overlap=suggestion_overlap,
        matched_pairs=len(matched_pairs),
        gold_risk_count=len(gold_risks),
        predicted_risk_count=len(contract.participants.get(participant, [])),
    )

    detail = {
        "contract_id": contract.contract_id,
        "participant": participant,
        "policy": policy,
        "clause_metrics": asdict(clause_metrics),
        "risk_metrics": asdict(risk_metrics),
        "matched_pairs": [
            {
                "gold": asdict(gold),
                "prediction": asdict(pred),
                "score": score,
            }
            for gold, pred, score in matched_pairs
        ],
        "unmatched_gold": [asdict(item) for item in unmatched_gold],
        "unmatched_prediction": [asdict(item) for item in unmatched_pred],
    }
    return metrics, detail, warnings


def _aggregate_metrics(items: list[ParticipantPolicyMetrics]) -> ParticipantPolicyMetrics:
    """跨合同聚合指标。"""

    participant = items[0].participant
    policy = items[0].policy

    clause_tp = sum(item.clause_metrics.tp for item in items)
    clause_fp = sum(item.clause_metrics.fp for item in items)
    clause_fn = sum(item.clause_metrics.fn for item in items)
    risk_tp = sum(item.risk_metrics.tp for item in items)
    risk_fp = sum(item.risk_metrics.fp for item in items)
    risk_fn = sum(item.risk_metrics.fn for item in items)
    matched_pairs = sum(item.matched_pairs for item in items)

    explanation_score = (
        sum(item.explanation_structure_score * item.matched_pairs for item in items) / matched_pairs
        if matched_pairs
        else 0.0
    )
    suggestion_score = (
        sum(item.suggestion_actionability_score * item.matched_pairs for item in items) / matched_pairs
        if matched_pairs
        else 0.0
    )
    title_overlap = (
        sum(item.exact_title_overlap * item.matched_pairs for item in items) / matched_pairs if matched_pairs else 0.0
    )
    suggestion_overlap = (
        sum(item.exact_suggestion_overlap * item.matched_pairs for item in items) / matched_pairs
        if matched_pairs
        else 0.0
    )

    return ParticipantPolicyMetrics(
        participant=participant,
        policy=policy,
        clause_metrics=_binary_metrics(clause_tp, clause_fp, clause_fn),
        risk_metrics=_binary_metrics(risk_tp, risk_fp, risk_fn),
        explanation_structure_score=explanation_score,
        suggestion_actionability_score=suggestion_score,
        exact_title_overlap=title_overlap,
        exact_suggestion_overlap=suggestion_overlap,
        matched_pairs=matched_pairs,
        gold_risk_count=sum(item.gold_risk_count for item in items),
        predicted_risk_count=sum(item.predicted_risk_count for item in items),
    )


def evaluate_dataset(
    dataset_path: Path,
    *,
    participants: list[str] | None = None,
    clause_match_threshold: float = 0.33,
    risk_match_threshold: float = 0.45,
) -> EvaluationPayload:
    """运行完整评估。"""

    dataset_meta, dataset_warnings, contracts = load_dataset(dataset_path)
    participants = participants or ["third_party", "final_applied"]

    warnings = list(dataset_warnings)
    by_key: dict[tuple[str, str], list[ParticipantPolicyMetrics]] = {}
    contract_results: list[dict[str, Any]] = []

    for contract in contracts:
        for participant in participants:
            for policy in ("adopted_only", "all_labeled"):
                metrics, detail, detail_warnings = evaluate_contract(
                    contract,
                    participant=participant,
                    policy=policy,
                    clause_match_threshold=clause_match_threshold,
                    risk_match_threshold=risk_match_threshold,
                )
                by_key.setdefault((participant, policy), []).append(metrics)
                contract_results.append(detail)
                warnings.extend(detail_warnings)

    participant_results = [
        _aggregate_metrics(items)
        for _, items in sorted(by_key.items(), key=lambda item: item[0])
        if items
    ]

    meta: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "dataset_path": str(dataset_path),
        "participants": participants,
        "dataset_meta": dataset_meta,
        "contract_count": len(contracts),
        "contract_ids": [contract.contract_id for contract in contracts],
        "clause_match_threshold": clause_match_threshold,
        "risk_match_threshold": risk_match_threshold,
    }
    if len(contracts) == 1:
        meta["single_contract"] = {
            "contract_id": contracts[0].contract_id,
            "source_files": contracts[0].source_files,
        }

    return EvaluationPayload(
        meta=meta,
        warnings=warnings,
        participant_results=participant_results,
        contract_results=contract_results,
    )
