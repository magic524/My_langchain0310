from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import BinaryMetrics, RiskItem


@dataclass(slots=True)
class MatchedRiskPair:
    """A matched gold/prediction pair for one contract."""

    gold: RiskItem
    prediction: RiskItem
    score: float


@dataclass(slots=True)
class PolicyAudit:
    """Detailed audit data for one evaluation policy."""

    policy: str
    clause_metrics: BinaryMetrics
    risk_metrics: BinaryMetrics
    matched_pairs: list[MatchedRiskPair]
    unmatched_gold: list[RiskItem]
    unmatched_prediction: list[RiskItem]
    explanation_structure_score: float
    suggestion_actionability_score: float
    gold_risk_count: int
    predicted_risk_count: int


@dataclass(slots=True)
class ContractAudit:
    """All data required to render one contract review section."""

    contract_id: str
    output_dir: Path
    source_files: dict[str, str]
    clause_lookup: dict[str, str]
    local_predictions: list[RiskItem]
    policy_audits: dict[str, PolicyAudit]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_risk(item: dict[str, Any]) -> RiskItem:
    return RiskItem(**item)


def _parse_metrics(item: dict[str, Any]) -> BinaryMetrics:
    return BinaryMetrics(
        precision=float(item.get("precision", 0.0)),
        recall=float(item.get("recall", 0.0)),
        f1=float(item.get("f1", 0.0)),
        tp=int(item.get("tp", 0)),
        fp=int(item.get("fp", 0)),
        fn=int(item.get("fn", 0)),
    )


def _policy_label(policy: str) -> str:
    if policy == "adopted_only":
        return "口径A（仅采纳 + 部分采纳）"
    if policy == "all_labeled":
        return "口径B（全部标签）"
    return policy


def _status_label(status: str) -> str:
    mapping = {
        "accept": "采纳",
        "partial": "部分采纳",
        "reject": "未采纳",
        "other": "其他",
    }
    return mapping.get(status, status or "-")


def _escape_cell(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "-"
    return normalized.replace("|", "\\|").replace("\n", "<br>")


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _find_participant_row(
    participant_rows: list[dict[str, Any]],
    *,
    participant: str,
    policy: str,
) -> dict[str, Any]:
    for row in participant_rows:
        if row.get("participant") == participant and row.get("policy") == policy:
            return row
    msg = f"Missing participant result for participant={participant}, policy={policy}"
    raise ValueError(msg)


def _find_contract_row(
    contract_rows: list[dict[str, Any]],
    *,
    participant: str,
    policy: str,
) -> dict[str, Any]:
    for row in contract_rows:
        if row.get("participant") == participant and row.get("policy") == policy:
            return row
    msg = f"Missing contract result for participant={participant}, policy={policy}"
    raise ValueError(msg)


def load_contract_audit(output_dir: Path) -> ContractAudit:
    """Load one `local_llm` evaluation directory into a structured audit view."""

    dataset_payload = _read_json(output_dir / "dataset_with_local_llm.json")
    prediction_payload = _read_json(output_dir / "local_llm_predictions.json")
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
    prediction_record = next(
        (
            item
            for item in prediction_payload
            if isinstance(item, dict) and str(item.get("contract_id", "")) == contract_id
        ),
        None,
    )
    if prediction_record is None:
        msg = f"Missing local_llm predictions for {contract_id}"
        raise ValueError(msg)

    contract_rows = [
        row
        for row in evaluation_payload.get("contract_results", [])
        if isinstance(row, dict) and str(row.get("contract_id", "")) == contract_id
    ]
    participant_rows = evaluation_payload.get("participant_results", [])

    policy_audits: dict[str, PolicyAudit] = {}
    for policy in ("adopted_only", "all_labeled"):
        contract_row = _find_contract_row(contract_rows, participant="local_llm", policy=policy)
        participant_row = _find_participant_row(participant_rows, participant="local_llm", policy=policy)
        policy_audits[policy] = PolicyAudit(
            policy=policy,
            clause_metrics=_parse_metrics(contract_row.get("clause_metrics", {})),
            risk_metrics=_parse_metrics(contract_row.get("risk_metrics", {})),
            matched_pairs=[
                MatchedRiskPair(
                    gold=_parse_risk(item["gold"]),
                    prediction=_parse_risk(item["prediction"]),
                    score=float(item.get("score", 0.0)),
                )
                for item in contract_row.get("matched_pairs", [])
                if isinstance(item, dict)
            ],
            unmatched_gold=[
                _parse_risk(item) for item in contract_row.get("unmatched_gold", []) if isinstance(item, dict)
            ],
            unmatched_prediction=[
                _parse_risk(item)
                for item in contract_row.get("unmatched_prediction", [])
                if isinstance(item, dict)
            ],
            explanation_structure_score=float(participant_row.get("explanation_structure_score", 0.0)),
            suggestion_actionability_score=float(participant_row.get("suggestion_actionability_score", 0.0)),
            gold_risk_count=int(participant_row.get("gold_risk_count", 0)),
            predicted_risk_count=int(participant_row.get("predicted_risk_count", 0)),
        )

    return ContractAudit(
        contract_id=contract_id,
        output_dir=output_dir,
        source_files={str(key): str(value) for key, value in (contract.get("source_files") or {}).items()},
        clause_lookup=clause_lookup,
        local_predictions=[
            _parse_risk(item) for item in prediction_record.get("risks", []) if isinstance(item, dict)
        ],
        policy_audits=policy_audits,
    )


def load_contract_audits(output_dirs: list[Path]) -> list[ContractAudit]:
    """Load and sort multiple audit directories."""

    audits = [load_contract_audit(path) for path in output_dirs]
    return sorted(audits, key=lambda item: item.contract_id)


def _build_risk_alignment_rows(audit: ContractAudit, policy_audit: PolicyAudit) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pair in policy_audit.matched_pairs:
        original_text = audit.clause_lookup.get(pair.gold.clause_id) or pair.gold.clause_text
        rows.append(
            {
                "result": "TP",
                "clause_id": pair.gold.clause_id or pair.prediction.clause_id,
                "original_clause": original_text,
                "gold_title": pair.gold.title,
                "gold_status": _status_label(pair.gold.status),
                "prediction_title": pair.prediction.title,
                "prediction_clause": pair.prediction.clause_text,
                "score": f"{pair.score:.4f}",
            }
        )
    for item in policy_audit.unmatched_prediction:
        original_text = audit.clause_lookup.get(item.clause_id) or item.clause_text
        rows.append(
            {
                "result": "FP",
                "clause_id": item.clause_id,
                "original_clause": original_text,
                "gold_title": "-",
                "gold_status": "-",
                "prediction_title": item.title,
                "prediction_clause": item.clause_text,
                "score": "-",
            }
        )
    for item in policy_audit.unmatched_gold:
        original_text = audit.clause_lookup.get(item.clause_id) or item.clause_text
        rows.append(
            {
                "result": "FN",
                "clause_id": item.clause_id,
                "original_clause": original_text,
                "gold_title": item.title,
                "gold_status": _status_label(item.status),
                "prediction_title": "-",
                "prediction_clause": "-",
                "score": "-",
            }
        )
    return rows


def _build_clause_summary_rows(audit: ContractAudit, policy_audit: PolicyAudit) -> list[dict[str, str]]:
    gold_by_clause: dict[str, list[RiskItem]] = {}
    pred_by_clause: dict[str, list[RiskItem]] = {}

    for pair in policy_audit.matched_pairs:
        gold_by_clause.setdefault(pair.gold.clause_id, []).append(pair.gold)
        pred_by_clause.setdefault(pair.prediction.clause_id, []).append(pair.prediction)
    for item in policy_audit.unmatched_gold:
        gold_by_clause.setdefault(item.clause_id, []).append(item)
    for item in policy_audit.unmatched_prediction:
        pred_by_clause.setdefault(item.clause_id, []).append(item)

    rows: list[dict[str, str]] = []
    clause_ids = sorted({*gold_by_clause.keys(), *pred_by_clause.keys()})
    for clause_id in clause_ids:
        gold_items = gold_by_clause.get(clause_id, [])
        pred_items = pred_by_clause.get(clause_id, [])
        if gold_items and pred_items:
            result = "TP"
        elif pred_items:
            result = "FP"
        else:
            result = "FN"
        rows.append(
            {
                "clause_id": clause_id,
                "original_clause": audit.clause_lookup.get(clause_id) or "-",
                "gold_count": str(len(gold_items)),
                "pred_count": str(len(pred_items)),
                "result": result,
                "gold_titles": "；".join(item.title for item in gold_items) or "-",
                "pred_titles": "；".join(item.title for item in pred_items) or "-",
            }
        )
    return rows


def _append_table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    lines.append("")


def _append_policy_section(lines: list[str], audit: ContractAudit, policy_audit: PolicyAudit) -> None:
    lines.append(f"### {_policy_label(policy_audit.policy)}")
    lines.append("")

    risk_rows = _build_risk_alignment_rows(audit, policy_audit)
    _append_table(
        lines,
        ["结果", "clause_id", "原文条款", "标签风险点", "标签状态", "模型风险点", "模型输出条款", "匹配分"],
        [
            [
                row["result"],
                row["clause_id"],
                row["original_clause"],
                row["gold_title"],
                row["gold_status"],
                row["prediction_title"],
                row["prediction_clause"],
                row["score"],
            ]
            for row in risk_rows
        ],
    )

    clause_rows = _build_clause_summary_rows(audit, policy_audit)
    _append_table(
        lines,
        ["clause_id", "原文条款", "Gold风险数", "Pred风险数", "条款结果", "Gold风险点", "Pred风险点"],
        [
            [
                row["clause_id"],
                row["original_clause"],
                row["gold_count"],
                row["pred_count"],
                row["result"],
                row["gold_titles"],
                row["pred_titles"],
            ]
            for row in clause_rows
        ],
    )

    lines.extend(
        [
            f"- Gold 风险点数: `{policy_audit.gold_risk_count}`",
            f"- Pred 风险点数: `{policy_audit.predicted_risk_count}`",
            f"- 风险点 TP / FP / FN = `{policy_audit.risk_metrics.tp}` / `{policy_audit.risk_metrics.fp}` / `{policy_audit.risk_metrics.fn}`",
            f"- 条款 TP / FP / FN = `{policy_audit.clause_metrics.tp}` / `{policy_audit.clause_metrics.fp}` / `{policy_audit.clause_metrics.fn}`",
            f"- 风险点 Precision = `{policy_audit.risk_metrics.tp} / ({policy_audit.risk_metrics.tp} + {policy_audit.risk_metrics.fp}) = {_pct(policy_audit.risk_metrics.precision)}`",
            f"- 风险点 Recall = `{policy_audit.risk_metrics.tp} / ({policy_audit.risk_metrics.tp} + {policy_audit.risk_metrics.fn}) = {_pct(policy_audit.risk_metrics.recall)}`",
            (
                "- 风险点 F1 = "
                f"`2 * {_pct(policy_audit.risk_metrics.precision)} * {_pct(policy_audit.risk_metrics.recall)} "
                f"/ ({_pct(policy_audit.risk_metrics.precision)} + {_pct(policy_audit.risk_metrics.recall)}) "
                f"= {_pct(policy_audit.risk_metrics.f1)}`"
            ),
            f"- 条款 Precision = `{policy_audit.clause_metrics.tp} / ({policy_audit.clause_metrics.tp} + {policy_audit.clause_metrics.fp}) = {_pct(policy_audit.clause_metrics.precision)}`",
            f"- 条款 Recall = `{policy_audit.clause_metrics.tp} / ({policy_audit.clause_metrics.tp} + {policy_audit.clause_metrics.fn}) = {_pct(policy_audit.clause_metrics.recall)}`",
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


def render_local_llm_review_report(audits: list[ContractAudit]) -> str:
    """Render a Markdown audit report for `local_llm` contract outputs."""

    lines = [
        "# local_llm 审阅版对照报告",
        "",
        "## 说明",
        "",
        "- 本报告只针对 `local_llm` 输出。",
        "- 每个实例先展示模型逐条输出与原合同条款的对照，再展示 `adopted_only` 与 `all_labeled` 两个口径下的 TP / FP / FN 明细和公式。",
        "- 表格里的“原文条款”来自 `dataset_with_local_llm.json -> contracts[].clauses` 中已经切好的原合同条款文本。",
        "",
        "## 汇总",
        "",
    ]

    summary_rows: list[list[str]] = []
    for audit in audits:
        for policy in ("adopted_only", "all_labeled"):
            policy_audit = audit.policy_audits[policy]
            summary_rows.append(
                [
                    audit.contract_id,
                    _policy_label(policy),
                    str(policy_audit.predicted_risk_count),
                    str(policy_audit.gold_risk_count),
                    f"{policy_audit.clause_metrics.tp}/{policy_audit.clause_metrics.fp}/{policy_audit.clause_metrics.fn}",
                    _pct(policy_audit.clause_metrics.precision),
                    _pct(policy_audit.clause_metrics.recall),
                    _pct(policy_audit.clause_metrics.f1),
                    f"{policy_audit.risk_metrics.tp}/{policy_audit.risk_metrics.fp}/{policy_audit.risk_metrics.fn}",
                    _pct(policy_audit.risk_metrics.precision),
                    _pct(policy_audit.risk_metrics.recall),
                    _pct(policy_audit.risk_metrics.f1),
                ]
            )
    _append_table(
        lines,
        [
            "合同",
            "口径",
            "Pred风险数",
            "Gold风险数",
            "Clause TP/FP/FN",
            "Clause P",
            "Clause R",
            "Clause F1",
            "Risk TP/FP/FN",
            "Risk P",
            "Risk R",
            "Risk F1",
        ],
        summary_rows,
    )

    for index, audit in enumerate(audits, start=1):
        lines.extend(
            [
                f"## {index}. {audit.contract_id}",
                "",
                f"- 输出目录: `{audit.output_dir}`",
                f"- 原合同 Word: `{audit.source_files.get('original_doc', '')}`",
                f"- 原合同 Markdown: `{audit.source_files.get('original_md', '')}`",
                f"- 采纳说明 Markdown: `{audit.source_files.get('adoption_md', '')}`",
                "",
                "### 模型逐条输出 vs 原文",
                "",
            ]
        )
        _append_table(
            lines,
            ["序号", "clause_id", "原文条款", "模型标题", "模型输出条款", "解释", "建议"],
            [
                [
                    str(item_index),
                    item.clause_id,
                    audit.clause_lookup.get(item.clause_id) or item.clause_text,
                    item.title,
                    item.clause_text,
                    item.explanation,
                    item.suggestion,
                ]
                for item_index, item in enumerate(audit.local_predictions, start=1)
            ],
        )
        _append_policy_section(lines, audit, audit.policy_audits["adopted_only"])
        _append_policy_section(lines, audit, audit.policy_audits["all_labeled"])

    return "\n".join(lines)


def write_local_llm_review_report(output_path: Path, audits: list[ContractAudit]) -> Path:
    """Write the rendered Markdown review report to disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_local_llm_review_report(audits), encoding="utf-8")
    return output_path
