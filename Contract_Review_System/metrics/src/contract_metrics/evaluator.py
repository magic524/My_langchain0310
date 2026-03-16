from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import EvalConfig
from .judge import JudgeThresholds, load_llm_runtime_config
from .matcher import align_risks_to_clauses
from .prediction_adapter import (
    load_agent_predictions_from_json,
    load_agent_predictions_from_markdown,
    merge_prediction_blocks,
)
from .scorer import build_policy_result, evaluate_clause_level
from .types import (
    ClauseRecord,
    ContractDataset,
    EvaluationPayload,
    ExplanationMetrics,
    IdentificationCounts,
    IdentificationMetrics,
    ParticipantPolicyResult,
    RiskEntry,
    SuggestionMetrics,
)


def _parse_clause(item: dict[str, Any]) -> ClauseRecord:
    return ClauseRecord(
        clause_id=str(item.get("clause_id", "")).strip(),
        clause_text=str(item.get("clause_text", "")).strip(),
    )


def _parse_risk(item: dict[str, Any]) -> RiskEntry:
    return RiskEntry(
        risk_id=str(item.get("risk_id", "")).strip(),
        contract_id=str(item.get("contract_id", "")).strip(),
        title=str(item.get("title", "")).strip(),
        clause_text=str(item.get("clause_text", "")).strip(),
        explanation=str(item.get("explanation", "")).strip(),
        suggestion=str(item.get("suggestion", "")).strip(),
        source_excerpt=str(item.get("source_excerpt", "")).strip(),
        status=str(item.get("status", "other")).strip() or "other",
        status_reason=str(item.get("status_reason", "")).strip(),
    )


def _parse_contract(item: dict[str, Any]) -> ContractDataset:
    baselines_payload = item.get("baselines") or {}
    baselines: dict[str, list[RiskEntry]] = {}
    if isinstance(baselines_payload, dict):
        for key, values in baselines_payload.items():
            if not isinstance(values, list):
                continue
            baselines[str(key)] = [_parse_risk(value) for value in values if isinstance(value, dict)]

    return ContractDataset(
        contract_id=str(item.get("contract_id", "")).strip(),
        source_files={
            str(key): str(value)
            for key, value in (item.get("source_files") or {}).items()
            if isinstance(key, str)
        },
        clauses=[_parse_clause(value) for value in (item.get("clauses") or []) if isinstance(value, dict)],
        labels=[_parse_risk(value) for value in (item.get("labels") or []) if isinstance(value, dict)],
        baselines=baselines,
    )


def load_dataset(dataset_path: Path) -> tuple[dict[str, Any], list[ContractDataset], list[str]]:
    """Load built dataset JSON.

    Args:
        dataset_path: Dataset path.

    Returns:
        Tuple of meta/contracts/warnings.
    """
    import json

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"Invalid dataset json root: {dataset_path}"
        raise ValueError(msg)

    meta = payload.get("meta") or {}
    warnings = [str(item) for item in (payload.get("warnings") or [])]
    contracts = [_parse_contract(item) for item in (payload.get("contracts") or []) if isinstance(item, dict)]
    return meta, contracts, warnings


def _aggregate_policy_results(results: list[ParticipantPolicyResult]) -> ParticipantPolicyResult:
    participant = results[0].participant
    policy = results[0].policy

    tp = sum(item.identification.counts.tp for item in results)
    fp = sum(item.identification.counts.fp for item in results)
    tn = sum(item.identification.counts.tn for item in results)
    fn = sum(item.identification.counts.fn for item in results)
    counts = IdentificationCounts(tp=tp, fp=fp, tn=tn, fn=fn)
    identification = IdentificationMetrics(
        accuracy=(tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) else 0.0,
        miss_rate=(fn / (tp + fn)) if (tp + fn) else 0.0,
        false_positive_rate=(fp / (fp + tn)) if (fp + tn) else 0.0,
        counts=counts,
    )

    exp_weight = sum(item.explanation.sample_size for item in results)
    explanation = ExplanationMetrics(
        direction_consistency=(
            sum(item.explanation.direction_consistency * item.explanation.sample_size for item in results) / exp_weight
            if exp_weight
            else 0.0
        ),
        accuracy=(
            sum(item.explanation.accuracy * item.explanation.sample_size for item in results) / exp_weight
            if exp_weight
            else 0.0
        ),
        completeness=(
            sum(item.explanation.completeness * item.explanation.sample_size for item in results) / exp_weight
            if exp_weight
            else 0.0
        ),
        sample_size=exp_weight,
    )

    sug_weight = sum(item.suggestion.sample_size for item in results)
    suggestion = SuggestionMetrics(
        direction_consistency=(
            sum(item.suggestion.direction_consistency * item.suggestion.sample_size for item in results) / sug_weight
            if sug_weight
            else 0.0
        ),
        content_accuracy=(
            sum(item.suggestion.content_accuracy * item.suggestion.sample_size for item in results) / sug_weight
            if sug_weight
            else 0.0
        ),
        completeness=(
            sum(item.suggestion.completeness * item.suggestion.sample_size for item in results) / sug_weight
            if sug_weight
            else 0.0
        ),
        sample_size=sug_weight,
    )

    return ParticipantPolicyResult(
        participant=participant,
        policy=policy,
        identification=identification,
        explanation=explanation,
        suggestion=suggestion,
    )


def evaluate_dataset(
    *,
    dataset_path: Path,
    eval_config: EvalConfig,
    agent_json_path: Path | None,
    agent_markdown_path: Path | None,
) -> EvaluationPayload:
    """Run full evaluation over dataset.

    Args:
        dataset_path: Built dataset path.
        eval_config: Evaluation config.
        agent_json_path: Optional agent JSON path.
        agent_markdown_path: Optional agent markdown path.

    Returns:
        Evaluation payload.
    """
    dataset_meta, contracts, dataset_warnings = load_dataset(dataset_path)
    warnings = list(dataset_warnings)

    contract_ids = [contract.contract_id for contract in contracts]

    agent_blocks = []
    if agent_json_path is not None and agent_json_path.exists():
        agent_blocks.extend(load_agent_predictions_from_json(json_path=agent_json_path, contract_ids=contract_ids))
    if agent_markdown_path is not None and agent_markdown_path.exists():
        agent_blocks.extend(
            load_agent_predictions_from_markdown(markdown_path=agent_markdown_path, contract_ids=contract_ids)
        )

    merged_agent_blocks = merge_prediction_blocks(agent_blocks)
    agent_by_contract = {item.contract_id: item.risks for item in merged_agent_blocks}

    threshold = eval_config.thresholds
    judge_thresholds = JudgeThresholds(
        direction_consistency_threshold=threshold.direction_consistency_threshold,
        explanation_accuracy_threshold=threshold.explanation_accuracy_threshold,
        suggestion_accuracy_threshold=threshold.suggestion_accuracy_threshold,
    )

    llm_runtime = None
    if eval_config.use_llm_judge:
        try:
            llm_runtime = load_llm_runtime_config()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"LLM judge disabled due to runtime error: {exc}")

    participant_contract_results: dict[tuple[str, str], list[ParticipantPolicyResult]] = {}
    contract_results: list[dict[str, Any]] = []

    for contract in contracts:
        labels_map = align_risks_to_clauses(
            contract.labels,
            contract.clauses,
            threshold=threshold.clause_match_threshold,
        )
        if labels_map.unmatched_risks:
            warnings.append(
                f"{contract.contract_id}: {len(labels_map.unmatched_risks)} label entries unmatched to clauses"
            )

        contract_detail: dict[str, Any] = {
            "contract_id": contract.contract_id,
            "participant_results": [],
            "unmatched": {
                "labels": [asdict(item) for item in labels_map.unmatched_risks],
            },
        }

        for participant in eval_config.participants:
            if participant in {"third_party", "final_applied"}:
                risks = contract.baselines.get(participant, [])
            elif participant == "agent":
                risks = agent_by_contract.get(contract.contract_id, [])
            else:
                warnings.append(f"Unknown participant ignored: {participant}")
                continue

            prediction_map = align_risks_to_clauses(
                risks,
                contract.clauses,
                threshold=threshold.clause_match_threshold,
            )
            if prediction_map.unmatched_risks:
                warnings.append(
                    f"{contract.contract_id}/{participant}: {len(prediction_map.unmatched_risks)} predictions unmatched"
                )

            contract_detail["unmatched"][participant] = [
                asdict(item) for item in prediction_map.unmatched_risks
            ]

            for policy in ("policy_a", "policy_b"):
                identification, explanation, suggestion, detail = evaluate_clause_level(
                    policy=policy,
                    clauses=contract.clauses,
                    labels_by_clause=labels_map.clause_to_risks,
                    predictions_by_clause=prediction_map.clause_to_risks,
                    thresholds=judge_thresholds,
                    use_llm_judge=bool(eval_config.use_llm_judge and llm_runtime is not None),
                    llm_runtime=llm_runtime,
                )
                result = build_policy_result(
                    participant=participant,
                    policy=policy,
                    identification=identification,
                    explanation=explanation,
                    suggestion=suggestion,
                )

                participant_contract_results.setdefault((participant, policy), []).append(result)
                contract_detail["participant_results"].append(
                    {
                        "participant": participant,
                        "policy": policy,
                        "metrics": asdict(result),
                        "detail": detail,
                    }
                )

        contract_results.append(contract_detail)

    participant_results: list[ParticipantPolicyResult] = []
    for key in sorted(participant_contract_results.keys()):
        items = participant_contract_results[key]
        if not items:
            continue
        participant_results.append(_aggregate_policy_results(items))

    return EvaluationPayload(
        meta={
            "generated_at": datetime.now().isoformat(),
            "dataset_path": str(dataset_path),
            "dataset_meta": dataset_meta,
            "participants": eval_config.participants,
            "use_llm_judge": bool(eval_config.use_llm_judge and llm_runtime is not None),
            "thresholds": asdict(eval_config.thresholds),
        },
        participant_results=participant_results,
        contract_results=contract_results,
        warnings=warnings,
    )
