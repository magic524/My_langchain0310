from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import BinaryMetrics, RiskItem


RISK_MARKER = "\u3010\u98ce\u9669\u70b9\u3011"
EXPLANATION_MARKER = "\u3010\u8bf4\u660e\u3011"
SUGGESTION_MARKER = "\u3010\u4fee\u6539\u5efa\u8bae\u3011"
COMMENT_MARKER = "\u3010\u6279\u6ce8"
STYLE_TAIL_MARKERS = (
    "\uff1b\u6837\u5f0f/",
    "\\| **\u4fee\u6539\u7406\u7531**",
    "| **\u4fee\u6539\u7406\u7531**",
)


@dataclass(slots=True)
class DisplayRisk:
    """Normalized risk text used in the reviewer-facing report."""

    risk_id: str
    contract_id: str
    clause_id: str
    title: str
    clause_text: str
    explanation: str
    suggestion: str
    status: str
    status_reason: str
    source_excerpt: str
    match_score: float


@dataclass(slots=True)
class MatchedRiskPair:
    """Matched gold and prediction pair."""

    gold: DisplayRisk
    prediction: DisplayRisk
    score: float


@dataclass(slots=True)
class ParticipantPolicyAudit:
    """Detailed evaluation evidence for one participant and one policy."""

    participant: str
    policy: str
    clause_metrics: BinaryMetrics
    risk_metrics: BinaryMetrics
    matched_pairs: list[MatchedRiskPair]
    unmatched_gold: list[DisplayRisk]
    unmatched_prediction: list[DisplayRisk]
    explanation_structure_score: float
    suggestion_actionability_score: float
    gold_risk_count: int
    predicted_risk_count: int


@dataclass(slots=True)
class ContractParallelAudit:
    """All contract data required for per-contract and overall reports."""

    contract_id: str
    output_dir: Path
    source_files: dict[str, str]
    clause_lookup: dict[str, str]
    gold_risks: list[DisplayRisk]
    local_llm_risks: list[DisplayRisk]
    third_party_risks: list[DisplayRisk]
    audits: dict[tuple[str, str], ParticipantPolicyAudit]


def _clean_embedded_field(text: str) -> str:
    value = str(text).strip()
    for marker in STYLE_TAIL_MARKERS:
        if marker in value:
            value = value.split(marker, 1)[0].strip()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ；】")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_metrics(item: dict[str, Any]) -> BinaryMetrics:
    return BinaryMetrics(
        precision=float(item.get("precision", 0.0)),
        recall=float(item.get("recall", 0.0)),
        f1=float(item.get("f1", 0.0)),
        tp=int(item.get("tp", 0)),
        fp=int(item.get("fp", 0)),
        fn=int(item.get("fn", 0)),
    )


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _escape_cell(text: str) -> str:
    normalized = " ".join(str(text).split())
    if not normalized:
        return "-"
    return normalized.replace("|", "\\|")


def _policy_label(policy: str) -> str:
    if policy == "adopted_only":
        return "口径A（仅采纳 + 部分采纳）"
    if policy == "all_labeled":
        return "口径B（全部标签）"
    return policy


def _participant_label(participant: str) -> str:
    if participant == "local_llm":
        return "local_llm"
    if participant == "third_party":
        return "third_party"
    return participant


def _status_label(status: str) -> str:
    mapping = {
        "accept": "采纳",
        "partial": "部分采纳",
        "reject": "未采纳",
        "other": "其他",
    }
    return mapping.get(status, status or "-")


def _extract_between(text: str, start: str, end_markers: tuple[str, ...]) -> str:
    if start not in text:
        return ""
    segment = text.split(start, 1)[1]
    end_positions = [segment.find(marker) for marker in end_markers if marker in segment]
    if end_positions:
        segment = segment[: min(end_positions)]
    return _clean_embedded_field(segment)


def normalize_display_risk(item: RiskItem | dict[str, Any]) -> DisplayRisk:
    """Normalize a risk item so mixed parser outputs remain readable."""

    risk = RiskItem(**item) if isinstance(item, dict) else item
    title = _clean_embedded_field(risk.title)
    clause_text = _clean_embedded_field(risk.clause_text)
    explanation = _clean_embedded_field(risk.explanation)
    suggestion = _clean_embedded_field(risk.suggestion)
    status_reason = _clean_embedded_field(risk.status_reason)
    source_excerpt = _clean_embedded_field(risk.source_excerpt)

    embedded_source = ""
    for candidate in (risk.title, risk.source_excerpt):
        if RISK_MARKER in candidate or EXPLANATION_MARKER in candidate or SUGGESTION_MARKER in candidate:
            embedded_source = candidate
            break

    if embedded_source:
        parsed_title = _extract_between(embedded_source, RISK_MARKER, (EXPLANATION_MARKER, SUGGESTION_MARKER))
        parsed_explanation = _extract_between(embedded_source, EXPLANATION_MARKER, (SUGGESTION_MARKER,))
        parsed_suggestion = _extract_between(embedded_source, SUGGESTION_MARKER, tuple())
        if parsed_title:
            title = parsed_title
        if not explanation and parsed_explanation:
            explanation = parsed_explanation
        if not suggestion and parsed_suggestion:
            suggestion = parsed_suggestion
        if not clause_text and COMMENT_MARKER in embedded_source:
            clause_text = _clean_embedded_field(embedded_source.split(COMMENT_MARKER, 1)[0])

    return DisplayRisk(
        risk_id=risk.risk_id,
        contract_id=risk.contract_id,
        clause_id=risk.clause_id,
        title=title or "-",
        clause_text=clause_text,
        explanation=explanation,
        suggestion=suggestion,
        status=risk.status,
        status_reason=status_reason,
        source_excerpt=source_excerpt,
        match_score=risk.match_score,
    )


def _merge_display_risk(preferred: DisplayRisk, fallback: DisplayRisk | None) -> DisplayRisk:
    if fallback is None:
        return preferred
    return DisplayRisk(
        risk_id=preferred.risk_id or fallback.risk_id,
        contract_id=preferred.contract_id or fallback.contract_id,
        clause_id=preferred.clause_id or fallback.clause_id,
        title=preferred.title if len(preferred.title) >= len(fallback.title) else fallback.title,
        clause_text=preferred.clause_text if len(preferred.clause_text) >= len(fallback.clause_text) else fallback.clause_text,
        explanation=preferred.explanation if len(preferred.explanation) >= len(fallback.explanation) else fallback.explanation,
        suggestion=preferred.suggestion if len(preferred.suggestion) >= len(fallback.suggestion) else fallback.suggestion,
        status=preferred.status or fallback.status,
        status_reason=preferred.status_reason if len(preferred.status_reason) >= len(fallback.status_reason) else fallback.status_reason,
        source_excerpt=preferred.source_excerpt if len(preferred.source_excerpt) >= len(fallback.source_excerpt) else fallback.source_excerpt,
        match_score=preferred.match_score or fallback.match_score,
    )


def _is_placeholder_title(text: str) -> bool:
    normalized = _clean_embedded_field(text)
    return not normalized or normalized == "-" or normalized.startswith("【风险点")


def _match_clause_id_from_text(
    paragraph_excerpt: str,
    match_candidates: list[str],
    clause_lookup: dict[str, str],
) -> str:
    search_texts = [paragraph_excerpt, *match_candidates]
    best_clause_id = ""
    best_score = -1
    for clause_id, clause_text in clause_lookup.items():
        clause_normalized = _normalize_text(clause_text)
        for candidate in search_texts:
            candidate_normalized = _normalize_text(candidate)
            if not candidate_normalized:
                continue
            if candidate_normalized in clause_normalized or clause_normalized in candidate_normalized:
                score = min(len(candidate_normalized), len(clause_normalized))
                if score > best_score:
                    best_score = score
                    best_clause_id = clause_id
    return best_clause_id


def _load_third_party_source_candidates(source_md: str, clause_lookup: dict[str, str]) -> list[DisplayRisk]:
    if not source_md:
        return []
    meta_path = Path(source_md).with_name("meta.json")
    if not meta_path.exists():
        return []
    payload = _read_json(meta_path)
    anchors = payload.get("comment_anchors")
    if not isinstance(anchors, list):
        return []

    candidates: list[DisplayRisk] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            continue
        comment_text = str(anchor.get("comment_text", ""))
        if RISK_MARKER not in comment_text:
            continue
        paragraph_excerpt = str(anchor.get("paragraph_excerpt", ""))
        clause_id = _match_clause_id_from_text(
            paragraph_excerpt,
            [str(item) for item in anchor.get("match_candidates", []) if isinstance(item, str)],
            clause_lookup,
        )
        normalized = normalize_display_risk(
            {
                "risk_id": f"third_party_source_anchor_{index}",
                "contract_id": "",
                "clause_id": clause_id,
                "title": comment_text,
                "clause_text": paragraph_excerpt,
                "explanation": "",
                "suggestion": "",
                "source_excerpt": comment_text,
            }
        )
        dedupe_key = (normalized.clause_id, normalized.title, normalized.explanation, normalized.suggestion)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(normalized)
    return candidates


def _select_best_source_risk(
    preferred: DisplayRisk,
    candidates: list[DisplayRisk],
    clause_lookup: dict[str, str],
) -> DisplayRisk | None:
    best_candidate: DisplayRisk | None = None
    best_score = -1
    preferred_clause_text = clause_lookup.get(preferred.clause_id, "")
    preferred_text = " ".join(
        item
        for item in (
            preferred.title,
            preferred.explanation,
            preferred.suggestion,
            preferred.source_excerpt,
            preferred.clause_text,
        )
        if item
    )
    preferred_text_normalized = _normalize_text(preferred_text)

    for candidate in candidates:
        score = 0
        if preferred.risk_id and candidate.risk_id == preferred.risk_id:
            score += 2
        if preferred.clause_id and candidate.clause_id == preferred.clause_id:
            score += 6
        elif preferred_clause_text:
            candidate_clause_normalized = _normalize_text(candidate.clause_text)
            preferred_clause_normalized = _normalize_text(preferred_clause_text)
            if candidate_clause_normalized and (
                candidate_clause_normalized in preferred_clause_normalized
                or preferred_clause_normalized in candidate_clause_normalized
            ):
                score += 5
        if not _is_placeholder_title(preferred.title):
            if candidate.title == preferred.title:
                score += 6
            elif candidate.title and (candidate.title in preferred.title or preferred.title in candidate.title):
                score += 4
        elif not _is_placeholder_title(candidate.title):
            score += 3
        for field in (candidate.title, candidate.explanation, candidate.suggestion):
            field_normalized = _normalize_text(field)
            if field_normalized and field_normalized in preferred_text_normalized:
                score += 3
        if score > best_score:
            best_score = score
            best_candidate = candidate
    return best_candidate if best_score > 0 else None


def _resolve_display_risk(
    item: RiskItem | dict[str, Any],
    *,
    raw_candidates: list[DisplayRisk],
    clause_lookup: dict[str, str],
) -> DisplayRisk:
    preferred = normalize_display_risk(item)
    fallback = _select_best_source_risk(preferred, raw_candidates, clause_lookup)
    return _merge_display_risk(preferred, fallback)


def _build_risk_text(items: list[DisplayRisk], *, include_status: bool) -> str:
    if not items:
        return "-"
    unique_items: list[DisplayRisk] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for item in items:
        dedupe_key = (item.title, item.explanation, item.suggestion, item.status, item.status_reason)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique_items.append(item)
    parts: list[str] = []
    for index, item in enumerate(unique_items, start=1):
        lines = [f"{index}. 标题：{item.title}"]
        if item.explanation:
            lines.append(f"说明：{item.explanation}")
        if item.suggestion:
            lines.append(f"建议：{item.suggestion}")
        if include_status:
            lines.append(f"采纳状态：{_status_label(item.status)}")
            if item.status_reason:
                lines.append(f"采纳原因：{item.status_reason}")
        parts.append("<br>".join(_escape_cell(line) for line in lines))
    return "<br><br>".join(parts)


def _build_original_text(audit: ContractParallelAudit, clause_id: str, fallback: str = "") -> str:
    return audit.clause_lookup.get(clause_id) or fallback or "-"


def _find_contract_row(rows: list[dict[str, Any]], *, participant: str, policy: str) -> dict[str, Any]:
    for row in rows:
        if row.get("participant") == participant and row.get("policy") == policy:
            return row
    msg = f"Missing contract row for participant={participant}, policy={policy}"
    raise ValueError(msg)


def _find_participant_row(rows: list[dict[str, Any]], *, participant: str, policy: str) -> dict[str, Any]:
    for row in rows:
        if row.get("participant") == participant and row.get("policy") == policy:
            return row
    msg = f"Missing participant row for participant={participant}, policy={policy}"
    raise ValueError(msg)


def _collect_predictions_for_participant(
    contract_rows: list[dict[str, Any]],
    *,
    participant: str,
    raw_candidates: list[DisplayRisk],
    clause_lookup: dict[str, str],
) -> list[DisplayRisk]:
    all_labeled_row = _find_contract_row(contract_rows, participant=participant, policy="all_labeled")
    risk_by_id: dict[str, DisplayRisk] = {}
    for pair in all_labeled_row.get("matched_pairs", []):
        prediction = _resolve_display_risk(
            pair["prediction"],
            raw_candidates=raw_candidates,
            clause_lookup=clause_lookup,
        )
        risk_by_id[prediction.risk_id] = prediction
    for item in all_labeled_row.get("unmatched_prediction", []):
        prediction = _resolve_display_risk(
            item,
            raw_candidates=raw_candidates,
            clause_lookup=clause_lookup,
        )
        risk_by_id[prediction.risk_id] = prediction
    return sorted(risk_by_id.values(), key=lambda value: (value.clause_id, value.risk_id))


def _collect_gold_risks(contract_rows: list[dict[str, Any]]) -> list[DisplayRisk]:
    all_labeled_row = _find_contract_row(contract_rows, participant="local_llm", policy="all_labeled")
    risk_by_id: dict[str, DisplayRisk] = {}
    for pair in all_labeled_row.get("matched_pairs", []):
        gold = normalize_display_risk(pair["gold"])
        risk_by_id[gold.risk_id] = gold
    for item in all_labeled_row.get("unmatched_gold", []):
        gold = normalize_display_risk(item)
        risk_by_id[gold.risk_id] = gold
    return sorted(risk_by_id.values(), key=lambda value: (value.clause_id, value.risk_id))


def _build_policy_audit(
    contract_rows: list[dict[str, Any]],
    participant_rows: list[dict[str, Any]],
    *,
    participant: str,
    policy: str,
    raw_candidates: list[DisplayRisk],
    clause_lookup: dict[str, str],
) -> ParticipantPolicyAudit:
    contract_row = _find_contract_row(contract_rows, participant=participant, policy=policy)
    participant_row = _find_participant_row(participant_rows, participant=participant, policy=policy)
    return ParticipantPolicyAudit(
        participant=participant,
        policy=policy,
        clause_metrics=_parse_metrics(contract_row.get("clause_metrics", {})),
        risk_metrics=_parse_metrics(contract_row.get("risk_metrics", {})),
        matched_pairs=[
            MatchedRiskPair(
                gold=normalize_display_risk(item["gold"]),
                prediction=_resolve_display_risk(
                    item["prediction"],
                    raw_candidates=raw_candidates,
                    clause_lookup=clause_lookup,
                ),
                score=float(item.get("score", 0.0)),
            )
            for item in contract_row.get("matched_pairs", [])
            if isinstance(item, dict)
        ],
        unmatched_gold=[
            normalize_display_risk(item) for item in contract_row.get("unmatched_gold", []) if isinstance(item, dict)
        ],
        unmatched_prediction=[
            _resolve_display_risk(
                item,
                raw_candidates=raw_candidates,
                clause_lookup=clause_lookup,
            )
            for item in contract_row.get("unmatched_prediction", [])
            if isinstance(item, dict)
        ],
        explanation_structure_score=float(participant_row.get("explanation_structure_score", 0.0)),
        suggestion_actionability_score=float(participant_row.get("suggestion_actionability_score", 0.0)),
        gold_risk_count=int(participant_row.get("gold_risk_count", 0)),
        predicted_risk_count=int(participant_row.get("predicted_risk_count", 0)),
    )


def load_parallel_audit(output_dir: Path) -> ContractParallelAudit:
    """Load one contract output directory into the three-way comparison structure."""

    dataset_payload = _read_json(output_dir / "dataset_with_local_llm.json")
    evaluation_payload = _read_json(output_dir / "evaluation_result.json")

    contracts = dataset_payload.get("contracts") or []
    if len(contracts) != 1:
        msg = f"Expected exactly one contract in {output_dir}"
        raise ValueError(msg)

    contract = contracts[0]
    contract_id = str(contract.get("contract_id", ""))
    clause_lookup = {
        str(item.get("clause_id", "")): str(item.get("clause_text", ""))
        for item in contract.get("clauses", [])
        if isinstance(item, dict)
    }
    contract_rows = [
        row
        for row in evaluation_payload.get("contract_results", [])
        if isinstance(row, dict) and str(row.get("contract_id", "")) == contract_id
    ]
    participant_rows = evaluation_payload.get("participant_results", [])
    participants_payload = contract.get("participants") or {}
    source_files = {str(key): str(value) for key, value in (contract.get("source_files") or {}).items()}
    raw_local_candidates = [
        normalize_display_risk(raw_item)
        for raw_item in participants_payload.get("local_llm", [])
        if isinstance(raw_item, dict)
    ]
    raw_third_party_candidates = _load_third_party_source_candidates(source_files.get("third_party_md", ""), clause_lookup)
    if not raw_third_party_candidates:
        raw_third_party_candidates = [
            normalize_display_risk(raw_item)
            for raw_item in participants_payload.get("third_party", [])
            if isinstance(raw_item, dict)
        ]

    audits = {
        (participant, policy): _build_policy_audit(
            contract_rows,
            participant_rows,
            participant=participant,
            policy=policy,
            raw_candidates=raw_local_candidates if participant == "local_llm" else raw_third_party_candidates,
            clause_lookup=clause_lookup,
        )
        for participant in ("local_llm", "third_party")
        for policy in ("adopted_only", "all_labeled")
    }

    return ContractParallelAudit(
        contract_id=contract_id,
        output_dir=output_dir,
        source_files=source_files,
        clause_lookup=clause_lookup,
        gold_risks=_collect_gold_risks(contract_rows),
        local_llm_risks=_collect_predictions_for_participant(
            contract_rows,
            participant="local_llm",
            raw_candidates=raw_local_candidates,
            clause_lookup=clause_lookup,
        ),
        third_party_risks=_collect_predictions_for_participant(
            contract_rows,
            participant="third_party",
            raw_candidates=raw_third_party_candidates,
            clause_lookup=clause_lookup,
        ),
        audits=audits,
    )


def load_parallel_audits(output_dirs: list[Path]) -> list[ContractParallelAudit]:
    """Load and sort multiple contract comparison outputs."""

    audits = [load_parallel_audit(path) for path in output_dirs]
    return sorted(audits, key=lambda item: item.contract_id)


def _append_table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    lines.append("")


def _third_party_source_note(source_path: str) -> str:
    if "批注" in source_path:
        return "带批注的合同全文 Markdown"
    if "审查意见书" in source_path:
        return "独立审查意见书 Markdown"
    return "第三方审查结果 Markdown"


def _build_parallel_clause_rows(audit: ContractParallelAudit) -> list[list[str]]:
    gold_by_clause: dict[str, list[DisplayRisk]] = {}
    local_by_clause: dict[str, list[DisplayRisk]] = {}
    third_by_clause: dict[str, list[DisplayRisk]] = {}

    for item in audit.gold_risks:
        gold_by_clause.setdefault(item.clause_id, []).append(item)
    for item in audit.local_llm_risks:
        local_by_clause.setdefault(item.clause_id, []).append(item)
    for item in audit.third_party_risks:
        third_by_clause.setdefault(item.clause_id, []).append(item)

    clause_ids = sorted({*gold_by_clause.keys(), *local_by_clause.keys(), *third_by_clause.keys()})
    rows: list[list[str]] = []
    for clause_id in clause_ids:
        rows.append(
            [
                clause_id,
                _build_original_text(audit, clause_id),
                _build_risk_text(local_by_clause.get(clause_id, []), include_status=False),
                _build_risk_text(third_by_clause.get(clause_id, []), include_status=False),
                _build_risk_text(gold_by_clause.get(clause_id, []), include_status=True),
            ]
        )
    return rows


def _build_alignment_rows(audit: ContractParallelAudit, policy_audit: ParticipantPolicyAudit) -> list[list[str]]:
    rows: list[list[str]] = []
    for pair in policy_audit.matched_pairs:
        rows.append(
            [
                "TP",
                pair.gold.clause_id or pair.prediction.clause_id,
                _build_original_text(audit, pair.gold.clause_id, pair.gold.clause_text),
                pair.gold.title,
                _status_label(pair.gold.status),
                pair.prediction.title,
                pair.prediction.explanation or "-",
                pair.prediction.suggestion or "-",
                f"{pair.score:.4f}",
            ]
        )
    for item in policy_audit.unmatched_prediction:
        rows.append(
            [
                "FP",
                item.clause_id,
                _build_original_text(audit, item.clause_id, item.clause_text),
                "-",
                "-",
                item.title,
                item.explanation or "-",
                item.suggestion or "-",
                "-",
            ]
        )
    for item in policy_audit.unmatched_gold:
        rows.append(
            [
                "FN",
                item.clause_id,
                _build_original_text(audit, item.clause_id, item.clause_text),
                item.title,
                _status_label(item.status),
                "-",
                "-",
                "-",
                "-",
            ]
        )
    return rows


def _build_clause_rows(audit: ContractParallelAudit, policy_audit: ParticipantPolicyAudit) -> list[list[str]]:
    gold_by_clause: dict[str, list[DisplayRisk]] = {}
    pred_by_clause: dict[str, list[DisplayRisk]] = {}

    for pair in policy_audit.matched_pairs:
        gold_by_clause.setdefault(pair.gold.clause_id, []).append(pair.gold)
        pred_by_clause.setdefault(pair.prediction.clause_id, []).append(pair.prediction)
    for item in policy_audit.unmatched_gold:
        gold_by_clause.setdefault(item.clause_id, []).append(item)
    for item in policy_audit.unmatched_prediction:
        pred_by_clause.setdefault(item.clause_id, []).append(item)

    rows: list[list[str]] = []
    clause_ids = sorted({*gold_by_clause.keys(), *pred_by_clause.keys()})
    for clause_id in clause_ids:
        gold_items = gold_by_clause.get(clause_id, [])
        pred_items = pred_by_clause.get(clause_id, [])
        result = "TP" if gold_items and pred_items else "FP" if pred_items else "FN"
        rows.append(
            [
                clause_id,
                _build_original_text(audit, clause_id),
                str(len(gold_items)),
                str(len(pred_items)),
                result,
                "；".join(item.title for item in gold_items) or "-",
                "；".join(item.title for item in pred_items) or "-",
            ]
        )
    return rows


def _append_metric_formula_block(lines: list[str], policy_audit: ParticipantPolicyAudit) -> None:
    risk_false_alarm = (
        _pct(1 - policy_audit.risk_metrics.precision)
        if (policy_audit.risk_metrics.tp + policy_audit.risk_metrics.fp)
        else "0.00%"
    )
    clause_false_alarm = (
        _pct(1 - policy_audit.clause_metrics.precision)
        if (policy_audit.clause_metrics.tp + policy_audit.clause_metrics.fp)
        else "0.00%"
    )
    lines.extend(
        [
            f"- Gold 风险点数: `{policy_audit.gold_risk_count}`",
            f"- Pred 风险点数: `{policy_audit.predicted_risk_count}`",
            f"- 风险点 TP / FP / FN = `{policy_audit.risk_metrics.tp}` / `{policy_audit.risk_metrics.fp}` / `{policy_audit.risk_metrics.fn}`",
            f"- 条款 TP / FP / FN = `{policy_audit.clause_metrics.tp}` / `{policy_audit.clause_metrics.fp}` / `{policy_audit.clause_metrics.fn}`",
            f"- 风险点 Precision = `{policy_audit.risk_metrics.tp} / ({policy_audit.risk_metrics.tp} + {policy_audit.risk_metrics.fp}) = {_pct(policy_audit.risk_metrics.precision)}`",
            f"- 风险点 Recall = `{policy_audit.risk_metrics.tp} / ({policy_audit.risk_metrics.tp} + {policy_audit.risk_metrics.fn}) = {_pct(policy_audit.risk_metrics.recall)}`",
            f"- 风险点 Miss Rate = `{policy_audit.risk_metrics.fn} / ({policy_audit.risk_metrics.tp} + {policy_audit.risk_metrics.fn}) = {_pct(1 - policy_audit.risk_metrics.recall)}`",
            f"- 风险点 False Alarm Rate = `{policy_audit.risk_metrics.fp} / ({policy_audit.risk_metrics.tp} + {policy_audit.risk_metrics.fp}) = {risk_false_alarm}`",
            (
                "- 风险点 F1 = "
                f"`2 * {_pct(policy_audit.risk_metrics.precision)} * {_pct(policy_audit.risk_metrics.recall)} "
                f"/ ({_pct(policy_audit.risk_metrics.precision)} + {_pct(policy_audit.risk_metrics.recall)}) "
                f"= {_pct(policy_audit.risk_metrics.f1)}`"
            ),
            f"- 条款 Precision = `{policy_audit.clause_metrics.tp} / ({policy_audit.clause_metrics.tp} + {policy_audit.clause_metrics.fp}) = {_pct(policy_audit.clause_metrics.precision)}`",
            f"- 条款 Recall = `{policy_audit.clause_metrics.tp} / ({policy_audit.clause_metrics.tp} + {policy_audit.clause_metrics.fn}) = {_pct(policy_audit.clause_metrics.recall)}`",
            f"- 条款 Miss Rate = `{policy_audit.clause_metrics.fn} / ({policy_audit.clause_metrics.tp} + {policy_audit.clause_metrics.fn}) = {_pct(1 - policy_audit.clause_metrics.recall)}`",
            f"- 条款 False Alarm Rate = `{policy_audit.clause_metrics.fp} / ({policy_audit.clause_metrics.tp} + {policy_audit.clause_metrics.fp}) = {clause_false_alarm}`",
            (
                "- 条款 F1 = "
                f"`2 * {_pct(policy_audit.clause_metrics.precision)} * {_pct(policy_audit.clause_metrics.recall)} "
                f"/ ({_pct(policy_audit.clause_metrics.precision)} + {_pct(policy_audit.clause_metrics.recall)}) "
                f"= {_pct(policy_audit.clause_metrics.f1)}`"
            ),
            f"- Explanation Structure Score = `{_pct(policy_audit.explanation_structure_score)}`",
            f"- Suggestion Actionability Score = `{_pct(policy_audit.suggestion_actionability_score)}`",
            "",
        ]
    )


def _append_glossary(lines: list[str]) -> None:
    lines.extend(
        [
            "## 指标说明",
            "",
            "- `TP`：预测命中。模型或第三方报出的风险点，与人工标签中的风险点成功匹配。",
            "- `FP`：误报。模型或第三方报出了风险点，但人工标签中没有对应风险点。",
            "- `FN`：漏报。人工标签里有风险点，但模型或第三方没有报出来。",
            "- `Clause` 指标：只看“这条条款是否被识别成风险条款”。",
            "- `Risk` 指标：看“具体风险点是否逐条对上”。",
            "- `Precision`：命中数占全部预测数的比例，越高表示误报越少。",
            "- `Recall`：命中数占全部标签数的比例，越高表示漏报越少。",
            "- `Miss Rate`：漏报率，等于 `FN / (TP + FN)`。",
            "- `False Alarm Rate`：误报率，等于 `FP / (TP + FP)`。",
            "- `F1`：综合 `Precision` 与 `Recall` 的调和平均。",
            "- `Explanation Structure Score`：只在已命中的风险点上计算，衡量解释文本结构是否完整。",
            "- `Suggestion Actionability Score`：只在已命中的风险点上计算，衡量建议是否具体可执行。",
            "",
        ]
    )


def render_contract_parallel_report(audit: ContractParallelAudit) -> str:
    """Render one contract-level Markdown comparison report."""

    third_party_md = audit.source_files.get("third_party_md", "")
    lines = [
        f"# {audit.contract_id} 三方并行对照报告",
        "",
        "## 数据来源",
        "",
        f"- 原合同 Markdown: `{audit.source_files.get('original_md', '')}`",
        f"- 原合同 Word: `{audit.source_files.get('original_doc', '')}`",
        f"- third_party 主来源文件: `{third_party_md}`",
        f"- third_party 文件形态判断: `{_third_party_source_note(third_party_md)}`",
        f"- 采纳说明 Markdown: `{audit.source_files.get('adoption_md', '')}`",
        f"- 最终人工修改稿 Markdown: `{audit.source_files.get('final_applied_md', '')}`",
        "",
        "## 原文 / local_llm / third_party / 采纳说明 并行对照",
        "",
    ]
    _append_table(
        lines,
        ["clause_id", "原文条款", "local_llm", "third_party", "采纳说明（标签）"],
        _build_parallel_clause_rows(audit),
    )

    for participant in ("local_llm", "third_party"):
        lines.extend([f"## {_participant_label(participant)} 指标对照", ""])
        for policy in ("adopted_only", "all_labeled"):
            policy_audit = audit.audits[(participant, policy)]
            _append_table(
                lines,
                ["结果", "clause_id", "原文条款", "标签风险点", "标签状态", f"{participant} 风险点", "解释", "建议", "匹配分"],
                _build_alignment_rows(audit, policy_audit),
            )
            _append_table(
                lines,
                ["clause_id", "原文条款", "Gold风险数", "Pred风险数", "条款结果", "Gold风险点", "Pred风险点"],
                _build_clause_rows(audit, policy_audit),
            )
            lines.extend([f"### {_participant_label(participant)} / {_policy_label(policy)} 计算过程", ""])
            _append_metric_formula_block(lines, policy_audit)

    _append_glossary(lines)
    return "\n".join(lines)


def write_contract_parallel_report(output_path: Path, audit: ContractParallelAudit) -> Path:
    """Write one contract-level report."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_contract_parallel_report(audit), encoding="utf-8")
    return output_path


def _aggregate_policy(
    audits: list[ContractParallelAudit],
    *,
    participant: str,
    policy: str,
) -> dict[str, float | int]:
    selected = [audit.audits[(participant, policy)] for audit in audits]
    contract_count = len(selected)
    clause_tp = sum(item.clause_metrics.tp for item in selected)
    clause_fp = sum(item.clause_metrics.fp for item in selected)
    clause_fn = sum(item.clause_metrics.fn for item in selected)
    risk_tp = sum(item.risk_metrics.tp for item in selected)
    risk_fp = sum(item.risk_metrics.fp for item in selected)
    risk_fn = sum(item.risk_metrics.fn for item in selected)
    matched_pairs = sum(len(item.matched_pairs) for item in selected)
    explanation_score = (
        sum(item.explanation_structure_score for item in selected) / contract_count
        if contract_count
        else 0.0
    )
    suggestion_score = (
        sum(item.suggestion_actionability_score for item in selected) / contract_count
        if contract_count
        else 0.0
    )
    clause_precision = clause_tp / (clause_tp + clause_fp) if (clause_tp + clause_fp) else 0.0
    clause_recall = clause_tp / (clause_tp + clause_fn) if (clause_tp + clause_fn) else 0.0
    clause_f1 = (
        2 * clause_precision * clause_recall / (clause_precision + clause_recall)
        if (clause_precision + clause_recall)
        else 0.0
    )
    risk_precision = risk_tp / (risk_tp + risk_fp) if (risk_tp + risk_fp) else 0.0
    risk_recall = risk_tp / (risk_tp + risk_fn) if (risk_tp + risk_fn) else 0.0
    risk_f1 = (
        2 * risk_precision * risk_recall / (risk_precision + risk_recall) if (risk_precision + risk_recall) else 0.0
    )
    return {
        "clause_tp": clause_tp,
        "clause_fp": clause_fp,
        "clause_fn": clause_fn,
        "risk_tp": risk_tp,
        "risk_fp": risk_fp,
        "risk_fn": risk_fn,
        "clause_precision": clause_precision,
        "clause_recall": clause_recall,
        "clause_f1": clause_f1,
        "risk_precision": risk_precision,
        "risk_recall": risk_recall,
        "risk_f1": risk_f1,
        "explanation_score": explanation_score,
        "suggestion_score": suggestion_score,
        "predicted_risk_count": sum(item.predicted_risk_count for item in selected),
        "gold_risk_count": sum(item.gold_risk_count for item in selected),
        "matched_pairs": matched_pairs,
        "contract_count": contract_count,
    }


def render_overall_summary_report(audits: list[ContractParallelAudit]) -> str:
    """Render the overall summary report for all contracts."""

    lines = [
        "# 20260317_word2md_eval 总体汇总与计算过程",
        "",
        "## third_party 主来源文件",
        "",
    ]
    _append_table(
        lines,
        ["合同", "third_party 主来源文件", "文件形态判断"],
        [
            [
                audit.contract_id,
                audit.source_files.get("third_party_md", ""),
                _third_party_source_note(audit.source_files.get("third_party_md", "")),
            ]
            for audit in audits
        ],
    )

    aggregate_cache: dict[tuple[str, str], dict[str, float | int]] = {}
    summary_rows: list[list[str]] = []
    for participant in ("local_llm", "third_party"):
        for policy in ("adopted_only", "all_labeled"):
            aggregate = _aggregate_policy(audits, participant=participant, policy=policy)
            aggregate_cache[(participant, policy)] = aggregate
            clause_false_alarm = (
                _pct(1 - float(aggregate["clause_precision"]))
                if (int(aggregate["clause_tp"]) + int(aggregate["clause_fp"]))
                else "0.00%"
            )
            risk_false_alarm = (
                _pct(1 - float(aggregate["risk_precision"]))
                if (int(aggregate["risk_tp"]) + int(aggregate["risk_fp"]))
                else "0.00%"
            )
            summary_rows.append(
                [
                    _participant_label(participant),
                    _policy_label(policy),
                    f"{aggregate['clause_tp']}/{aggregate['clause_fp']}/{aggregate['clause_fn']}",
                    _pct(float(aggregate["clause_precision"])),
                    _pct(float(aggregate["clause_recall"])),
                    _pct(1 - float(aggregate["clause_recall"])),
                    clause_false_alarm,
                    f"{aggregate['risk_tp']}/{aggregate['risk_fp']}/{aggregate['risk_fn']}",
                    _pct(float(aggregate["risk_precision"])),
                    _pct(float(aggregate["risk_recall"])),
                    _pct(1 - float(aggregate["risk_recall"])),
                    risk_false_alarm,
                    _pct(float(aggregate["risk_f1"])),
                    _pct(float(aggregate["explanation_score"])),
                    _pct(float(aggregate["suggestion_score"])),
                ]
            )
    lines.extend(["## 总体结果", ""])
    lines.extend(["说明：`Explanation Score` 与 `Suggestion Score` 的总体值沿用 [20260317_word2md_eval_report](./20260317_word2md_eval_report.md) 口径，按 3 份合同做简单平均。", ""])
    _append_table(
        lines,
        [
            "参与方",
            "口径",
            "Clause TP/FP/FN",
            "Clause Precision",
            "Clause Recall",
            "Clause Miss Rate",
            "Clause False Alarm Rate",
            "Risk TP/FP/FN",
            "Risk Precision",
            "Risk Recall",
            "Risk Miss Rate",
            "Risk False Alarm Rate",
            "Risk F1",
            "Explanation Score",
            "Suggestion Score",
        ],
        summary_rows,
    )

    lines.extend(["## 分合同结果", ""])
    _append_table(
        lines,
        ["合同", "参与方", "口径", "Clause TP/FP/FN", "Clause F1", "Risk TP/FP/FN", "Risk F1"],
        [
            [
                audit.contract_id,
                _participant_label(participant),
                _policy_label(policy),
                f"{audit.audits[(participant, policy)].clause_metrics.tp}/{audit.audits[(participant, policy)].clause_metrics.fp}/{audit.audits[(participant, policy)].clause_metrics.fn}",
                _pct(audit.audits[(participant, policy)].clause_metrics.f1),
                f"{audit.audits[(participant, policy)].risk_metrics.tp}/{audit.audits[(participant, policy)].risk_metrics.fp}/{audit.audits[(participant, policy)].risk_metrics.fn}",
                _pct(audit.audits[(participant, policy)].risk_metrics.f1),
            ]
            for audit in audits
            for participant in ("local_llm", "third_party")
            for policy in ("adopted_only", "all_labeled")
        ],
    )

    lines.extend(["## 计算过程", ""])
    for participant in ("local_llm", "third_party"):
        for policy in ("adopted_only", "all_labeled"):
            aggregate = aggregate_cache[(participant, policy)]
            clause_false_alarm = (
                _pct(1 - float(aggregate["clause_precision"]))
                if (int(aggregate["clause_tp"]) + int(aggregate["clause_fp"]))
                else "0.00%"
            )
            risk_false_alarm = (
                _pct(1 - float(aggregate["risk_precision"]))
                if (int(aggregate["risk_tp"]) + int(aggregate["risk_fp"]))
                else "0.00%"
            )
            explanation_formula = " + ".join(
                _pct(audit.audits[(participant, policy)].explanation_structure_score)
                for audit in audits
            )
            suggestion_formula = " + ".join(
                _pct(audit.audits[(participant, policy)].suggestion_actionability_score)
                for audit in audits
            )
            lines.extend(
                [
                    f"### {_participant_label(participant)} / {_policy_label(policy)}",
                    "",
                    f"- Clause TP = {' + '.join(str(audit.audits[(participant, policy)].clause_metrics.tp) for audit in audits)} = `{aggregate['clause_tp']}`",
                    f"- Clause FP = {' + '.join(str(audit.audits[(participant, policy)].clause_metrics.fp) for audit in audits)} = `{aggregate['clause_fp']}`",
                    f"- Clause FN = {' + '.join(str(audit.audits[(participant, policy)].clause_metrics.fn) for audit in audits)} = `{aggregate['clause_fn']}`",
                    f"- Clause Precision = `{aggregate['clause_tp']} / ({aggregate['clause_tp']} + {aggregate['clause_fp']}) = {_pct(float(aggregate['clause_precision']))}`",
                    f"- Clause Recall = `{aggregate['clause_tp']} / ({aggregate['clause_tp']} + {aggregate['clause_fn']}) = {_pct(float(aggregate['clause_recall']))}`",
                    f"- Clause Miss Rate = `{aggregate['clause_fn']} / ({aggregate['clause_tp']} + {aggregate['clause_fn']}) = {_pct(1 - float(aggregate['clause_recall']))}`",
                    f"- Clause False Alarm Rate = `{aggregate['clause_fp']} / ({aggregate['clause_tp']} + {aggregate['clause_fp']}) = {clause_false_alarm}`",
                    f"- Risk TP = {' + '.join(str(audit.audits[(participant, policy)].risk_metrics.tp) for audit in audits)} = `{aggregate['risk_tp']}`",
                    f"- Risk FP = {' + '.join(str(audit.audits[(participant, policy)].risk_metrics.fp) for audit in audits)} = `{aggregate['risk_fp']}`",
                    f"- Risk FN = {' + '.join(str(audit.audits[(participant, policy)].risk_metrics.fn) for audit in audits)} = `{aggregate['risk_fn']}`",
                    f"- Risk Precision = `{aggregate['risk_tp']} / ({aggregate['risk_tp']} + {aggregate['risk_fp']}) = {_pct(float(aggregate['risk_precision']))}`",
                    f"- Risk Recall = `{aggregate['risk_tp']} / ({aggregate['risk_tp']} + {aggregate['risk_fn']}) = {_pct(float(aggregate['risk_recall']))}`",
                    f"- Risk Miss Rate = `{aggregate['risk_fn']} / ({aggregate['risk_tp']} + {aggregate['risk_fn']}) = {_pct(1 - float(aggregate['risk_recall']))}`",
                    f"- Risk False Alarm Rate = `{aggregate['risk_fp']} / ({aggregate['risk_tp']} + {aggregate['risk_fp']}) = {risk_false_alarm}`",
                    (
                        "- Risk F1 = "
                        f"`2 * {_pct(float(aggregate['risk_precision']))} * {_pct(float(aggregate['risk_recall']))} "
                        f"/ ({_pct(float(aggregate['risk_precision']))} + {_pct(float(aggregate['risk_recall']))}) "
                        f"= {_pct(float(aggregate['risk_f1']))}`"
                    ),
                    (
                        f"- Explanation Score = `({explanation_formula}) / {aggregate['contract_count']} = {_pct(float(aggregate['explanation_score']))}`"
                        if int(aggregate["contract_count"])
                        else "- Explanation Score = `0.00%`"
                    ),
                    (
                        f"- Suggestion Score = `({suggestion_formula}) / {aggregate['contract_count']} = {_pct(float(aggregate['suggestion_score']))}`"
                        if int(aggregate["contract_count"])
                        else "- Suggestion Score = `0.00%`"
                    ),
                    "",
                ]
            )

    _append_glossary(lines)
    return "\n".join(lines)


def write_overall_summary_report(output_path: Path, audits: list[ContractParallelAudit]) -> Path:
    """Write the overall summary report."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_overall_summary_report(audits), encoding="utf-8")
    return output_path
