from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "outputs_fix2"
    / "20260317_word2md_eval_third_party_fix2_20260318"
    / "contract_runs"
    / "1-品牌球馆冠名合作协议"
    / "dataset_with_local_llm.json"
)
DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent / "template.json"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


@dataclass(slots=True)
class RuntimeConfig:
    """Runtime config for local ChatOpenAI endpoint."""

    openai_api_key: str = "EMPTY"
    openai_api_base: str = "http://10.130.61.231:8001/v1"
    model_name: str = "InstructModel"
    temperature: float = 0.7
    top_k: int = 20
    enable_thinking: bool = True
    request_timeout: float = 60.0


def _compact_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_text(text: Any) -> str:
    cleaned = re.sub(r"[`*_>#\[\]()~|]", "", str(text or ""))
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.strip().lower()


def _text_similarity(left: Any, right: Any) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(a=left_norm, b=right_norm).ratio()


def _best_pair_score(local_risk: dict[str, Any], third_risk: dict[str, Any]) -> float:
    return max(
        _text_similarity(local_risk.get("title", ""), third_risk.get("title", "")),
        _text_similarity(local_risk.get("explanation", ""), third_risk.get("explanation", "")),
        _text_similarity(local_risk.get("suggestion", ""), third_risk.get("suggestion", "")),
        _text_similarity(local_risk.get("clause_text", ""), third_risk.get("clause_text", "")),
    )


def _extract_first_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        chunk = text[start : end + 1]
        parsed = json.loads(chunk)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("LLM output is not a valid JSON object")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_template_match(template_path: Path) -> dict[str, Any]:
    template = _load_json(template_path)
    match_template = template.get("match")
    if not isinstance(match_template, dict):
        raise ValueError("template.json 缺少 match 对象")
    return match_template


def _read_template_payload(template_path: Path) -> dict[str, Any]:
    template = _load_json(template_path)
    if not isinstance(template, dict):
        raise ValueError("template.json 结构错误")
    if not isinstance(template.get("match"), dict):
        raise ValueError("template.json 缺少 match 对象")
    return template


def _ensure_langchain_chatopenai() -> tuple[Any, Any, Any]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = (
            "缺少依赖 langchain_openai 或 langchain_core。"
            "请先执行: conda activate langchain"
        )
        raise RuntimeError(msg) from exc
    return ChatOpenAI, SystemMessage, HumanMessage


def _build_llm_judge_prompt(
    contract_id: str,
    clause_text: str,
    local_risk: dict[str, Any],
    third_risk: dict[str, Any],
    template_match: dict[str, Any],
) -> str:
    fields = ", ".join(template_match.keys())
    template_stub = {
        key: ("" if "reason" in key or key.endswith("name") or key.endswith("title") else "1 or 0")
        for key in template_match
    }
    if "predicted_risk_point_title" in template_stub:
        template_stub["predicted_risk_point_title"] = _compact_text(local_risk.get("title", ""))
    if "matched_true_label_risk_point_title" in template_stub:
        template_stub["matched_true_label_risk_point_title"] = _compact_text(third_risk.get("title", ""))
    if "matched_true_label_risk_point_name" in template_stub:
        template_stub["matched_true_label_risk_point_name"] = _compact_text(third_risk.get("title", ""))

    return f"""
你是合同审查评估专家。请判断“本地模型风险点”是否与“第三方平台风险点”接近。

合同ID: {contract_id}
条款原文: {_compact_text(clause_text)}

本地模型输出:
- title: {_compact_text(local_risk.get('title', ''))}
- explanation: {_compact_text(local_risk.get('explanation', ''))}
- suggestion: {_compact_text(local_risk.get('suggestion', ''))}

第三方平台输出:
- title: {_compact_text(third_risk.get('title', ''))}
- explanation: {_compact_text(third_risk.get('explanation', ''))}
- suggestion: {_compact_text(third_risk.get('suggestion', ''))}

请只输出一个 JSON 对象，字段必须严格为: {fields}
规则:
1) 所有 *_consistency / *_accuracy / *_completeness 只允许输出字符串 "1" 或 "0"。
2) 每个 *_reason 字段必须给出简洁中文理由。
3) 不要输出任何额外字段或解释。

示例结构(仅示例，按实际判断填写):
{json.dumps(template_stub, ensure_ascii=False, indent=2)}
""".strip()


def _normalize_match_result(raw_match: dict[str, Any], template_match: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in template_match.keys():
        value = raw_match.get(key, "")
        if key.endswith("_consistency") or key.endswith("_accuracy") or key.endswith("_completeness"):
            value = "1" if str(value).strip() in {"1", "true", "True"} else "0"
        else:
            value = _compact_text(value)
        normalized[key] = value
    return normalized


def _index_clause_text(contract: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in contract.get("clauses", []):
        if not isinstance(item, dict):
            continue
        clause_id = str(item.get("clause_id", "")).strip()
        clause_text = str(item.get("clause_text", "")).strip()
        if clause_id:
            lookup[clause_id] = clause_text
    return lookup


def _best_third_party_for_local(local_risk: dict[str, Any], third_party_risks: list[dict[str, Any]]) -> tuple[int, float]:
    best_idx = -1
    best_score = -1.0
    for idx, candidate in enumerate(third_party_risks):
        score = _best_pair_score(local_risk, candidate)
        if score > best_score:
            best_idx = idx
            best_score = score
    return best_idx, max(best_score, 0.0)


def evaluate_dataset_with_llm(
    *,
    dataset_path: Path,
    template_path: Path,
    output_dir: Path,
    runtime: RuntimeConfig,
    match_threshold: float,
    max_items: int,
) -> Path:
    ChatOpenAI, SystemMessage, HumanMessage = _ensure_langchain_chatopenai()

    payload = _load_json(dataset_path)
    contracts = payload.get("contracts", [])
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("dataset_with_local_llm.json 中 contracts 为空")

    contract = contracts[0]
    contract_id = str(contract.get("contract_id", ""))
    participants = contract.get("participants") or {}
    if not isinstance(participants, dict):
        raise ValueError("participants 字段格式错误")

    local_risks = participants.get("local_llm") or []
    third_risks = participants.get("third_party") or []
    if not isinstance(local_risks, list) or not isinstance(third_risks, list):
        raise ValueError("local_llm / third_party 字段格式错误")

    template_payload = _read_template_payload(template_path)
    template_match = template_payload["match"]

    fp_template = template_payload.get("false_positive")
    fn_template = template_payload.get("false_negative")
    fp_names_key = "predicted_risk_point_names"
    fn_names_key = "missed_risk_point_names"
    if isinstance(fp_template, dict):
        for key, value in fp_template.items():
            if isinstance(value, list):
                fp_names_key = key
                break
    if isinstance(fn_template, dict):
        for key, value in fn_template.items():
            if isinstance(value, list):
                fn_names_key = key
                break
    clause_lookup = _index_clause_text(contract)

    llm_local = ChatOpenAI(
        openai_api_key=runtime.openai_api_key,
        openai_api_base=runtime.openai_api_base,
        model_name=runtime.model_name,
        temperature=runtime.temperature,
        request_timeout=runtime.request_timeout,
        extra_body={
            "top_k": runtime.top_k,
            "chat_template_kwargs": {"enable_thinking": runtime.enable_thinking},
        },
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw_llm_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)

    process_logs: list[str] = []
    process_logs.append("step1: 读取数据集与模板")
    process_logs.append(f"step2: local_llm 风险点数={len(local_risks)}, third_party 风险点数={len(third_risks)}")

    match_results: list[dict[str, Any]] = []
    matched_third_indices: set[int] = set()
    false_positive_names: list[str] = []
    llm_error_count = 0

    limited_local = local_risks[:max_items] if max_items > 0 else local_risks
    process_logs.append(f"step3: 本次评估 local_llm 条目数={len(limited_local)}")

    for idx, local_risk in enumerate(limited_local, start=1):
        if not isinstance(local_risk, dict):
            continue

        best_idx, best_score = _best_third_party_for_local(local_risk, third_risks)
        if best_idx < 0:
            false_positive_names.append(_compact_text(local_risk.get("title", "")))
            continue

        best_third = third_risks[best_idx]
        clause_id = str(local_risk.get("clause_id", "")).strip() or str(best_third.get("clause_id", "")).strip()
        clause_text = clause_lookup.get(clause_id, "")
        if not clause_text:
            clause_text = _compact_text(local_risk.get("clause_text", "")) or _compact_text(best_third.get("clause_text", ""))

        if best_score < match_threshold:
            false_positive_names.append(_compact_text(local_risk.get("title", "")))
            continue

        prompt = _build_llm_judge_prompt(
            contract_id=contract_id,
            clause_text=clause_text,
            local_risk=local_risk,
            third_risk=best_third,
            template_match=template_match,
        )
        try:
            response = llm_local.invoke([
                SystemMessage(content="你是严谨的合同审查评估助手，只输出 JSON。"),
                HumanMessage(content=prompt),
            ])
            response_text = response.content if isinstance(response.content, str) else str(response.content)
        except Exception as exc:  # noqa: BLE001
            llm_error_count += 1
            process_logs.append(f"step3.error: local风险点#{idx} 调用失败: {type(exc).__name__}")
            false_positive_names.append(_compact_text(local_risk.get("title", "")))
            continue

        raw_path = raw_dir / f"match_{idx:03d}.txt"
        raw_path.write_text(response_text, encoding="utf-8")

        parsed = _extract_first_json_object(response_text)
        normalized_match = _normalize_match_result(parsed, template_match)
        if "predicted_risk_point_title" in normalized_match:
            normalized_match["predicted_risk_point_title"] = _compact_text(local_risk.get("title", ""))
        if "matched_true_label_risk_point_title" in normalized_match:
            normalized_match["matched_true_label_risk_point_title"] = _compact_text(best_third.get("title", ""))
        if "matched_true_label_risk_point_name" in normalized_match:
            normalized_match["matched_true_label_risk_point_name"] = _compact_text(best_third.get("title", ""))

        match_results.append(
            {
                "match": normalized_match,
                "pair_meta": {
                    "local_risk_id": str(local_risk.get("risk_id", "")),
                    "third_party_risk_id": str(best_third.get("risk_id", "")),
                    "clause_id": clause_id,
                    "similarity": round(best_score, 4),
                },
            }
        )
        matched_third_indices.add(best_idx)

    false_negative_names: list[str] = []
    for idx, third_risk in enumerate(third_risks):
        if idx not in matched_third_indices:
            false_negative_names.append(_compact_text(third_risk.get("title", "")))

    result = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "dataset_path": str(dataset_path),
            "template_path": str(template_path),
            "contract_id": contract_id,
            "model_config": {
                "openai_api_base": runtime.openai_api_base,
                "model_name": runtime.model_name,
                "temperature": runtime.temperature,
                "top_k": runtime.top_k,
                "enable_thinking": runtime.enable_thinking,
            },
            "match_threshold": match_threshold,
            "max_items": max_items,
            "llm_error_count": llm_error_count,
        },
        "process_log": process_logs,
        "match_results": match_results,
        "false_positive": {
            "count": len(false_positive_names),
            fp_names_key: false_positive_names,
        },
        "false_negative": {
            "count": len(false_negative_names),
            fn_names_key: false_negative_names,
        },
    }

    result_path = output_dir / "quality_eval_by_template.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    console_lines = [
        "[流程] step1 读取 dataset/template 完成",
        f"[流程] step2 local_llm={len(local_risks)}, third_party={len(third_risks)}",
        f"[流程] step3 参与评估 local_llm 条目={len(limited_local)}",
        f"[流程] step4 生成 match={len(match_results)} FP={len(false_positive_names)} FN={len(false_negative_names)}",
        f"[流程] step4.1 LLM调用失败数={llm_error_count}",
        f"[输出] {result_path}",
    ]
    print("\n".join(console_lines))

    return result_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare local_llm vs third_party by LLM judge and output template-based JSON"
    )
    parser.add_argument(
        "--dataset-path",
        type=str,
        default=str(DEFAULT_DATASET_PATH),
        help="Path to dataset_with_local_llm.json",
    )
    parser.add_argument(
        "--template-path",
        type=str,
        default=str(DEFAULT_TEMPLATE_PATH),
        help="Path to template.json",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for evaluation results",
    )
    parser.add_argument("--openai-api-base", type=str, default="http://10.130.61.231:8001/v1")
    parser.add_argument("--model-name", type=str, default="InstructModel")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--enable-thinking", action="store_true", default=True)
    parser.add_argument("--disable-thinking", action="store_true", default=False)
    parser.add_argument("--match-threshold", type=float, default=0.45)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Max local_llm risks to evaluate (0 means all)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    enable_thinking = args.enable_thinking and (not args.disable_thinking)
    runtime = RuntimeConfig(
        openai_api_key="EMPTY",
        openai_api_base=args.openai_api_base,
        model_name=args.model_name,
        temperature=args.temperature,
        top_k=args.top_k,
        enable_thinking=enable_thinking,
        request_timeout=args.request_timeout,
    )

    evaluate_dataset_with_llm(
        dataset_path=Path(args.dataset_path).resolve(),
        template_path=Path(args.template_path).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        runtime=runtime,
        match_threshold=args.match_threshold,
        max_items=args.max_items,
    )


if __name__ == "__main__":
    main()
