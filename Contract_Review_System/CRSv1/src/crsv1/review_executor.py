from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from Contract_Review_System.common.local_llm_client import RuntimeConfig, build_payload, post_chat_request

from .background_brief import parse_background_brief
from .review_prompt_builder import build_background_messages, build_clause_review_messages
from .runtime_types import (
    ClauseNode,
    ClauseReviewResult,
    ClauseReviewTask,
    ClauseRisk,
    ContractBackgroundBrief,
    ReviewPromptContext,
)
from .text_utils import safe_filename


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    # 调试请求与中间结果统一以 UTF-8 JSON 落盘。
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_debug_request(path: Path, runtime: RuntimeConfig, messages: list[tuple[str, str]], note: str) -> None:
    # 调试文件仅保留消息预览，避免把超长全文重复写入。
    payload = build_payload(runtime, messages, extra_body=runtime.extra_body)
    sanitized = dict(payload)
    sanitized["messages"] = [
        {
            "role": item.get("role"),
            "content_preview": str(item.get("content", ""))[:800],
            "content_length": len(str(item.get("content", ""))),
        }
        for item in payload.get("messages", [])
        if isinstance(item, dict)
    ]
    _write_json(path, {"note": note, "request": sanitized})


def send_chat(runtime: RuntimeConfig, messages: list[tuple[str, str]]) -> str:
    """通过统一的本地 LLM HTTP 层发送对话请求。"""

    payload = build_payload(runtime, messages, extra_body=runtime.extra_body)
    return post_chat_request(runtime, payload)


def run_background_brief(
    contract_id: str,
    contract_text: str,
    runtime: RuntimeConfig,
    prompt_context: ReviewPromptContext,
    *,
    raw_dir: Path,
    debug_dir: Path,
    reuse_raw_response: bool = False,
    log_callback: Any | None = None,
) -> tuple[ContractBackgroundBrief, str]:
    """生成合同级背景摘要。"""

    safe_contract_id = safe_filename(contract_id)
    raw_path = raw_dir / f"{safe_contract_id}.background.txt"
    debug_path = debug_dir / f"{safe_contract_id}.background.request.json"
    if log_callback is not None:
        log_callback(f"CRSv1：开始生成合同背景摘要：{contract_id}")
    if reuse_raw_response and raw_path.exists():
        # 支持复用历史响应，便于离线复盘和调试。
        raw_text = raw_path.read_text(encoding="utf-8")
    else:
        messages = build_background_messages(contract_text, prompt_context)
        _write_debug_request(debug_path, runtime, messages, "background_brief")
        raw_text = send_chat(runtime, messages)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_text, encoding="utf-8")
    if log_callback is not None:
        log_callback(f"CRSv1：完成合同背景摘要：{contract_id}")
    return parse_background_brief(raw_text, contract_text), str(raw_path)


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    # 兼容模型输出中的 <think> 前缀或额外文本，尽量提取 JSON 主体。
    stripped = raw_text.strip()
    if not stripped:
        return {"risks": []}
    if "</think>" in stripped:
        stripped = stripped.split("</think>")[-1].strip()
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(stripped)
        if isinstance(payload, dict) and "risks" in payload:
            return payload
    except json.JSONDecodeError:
        pass

    brace_indexes = [index for index, char in enumerate(stripped) if char == "{"]
    fallback_payload: dict[str, Any] | None = None
    for start in reversed(brace_indexes):
        candidate = stripped[start:]
        try:
            payload, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            if "risks" in payload:
                return payload
            if fallback_payload is None:
                fallback_payload = payload
    salvaged_risks = _salvage_risk_items(stripped)
    if salvaged_risks:
        return {"risks": salvaged_risks}
    if fallback_payload is not None:
        return fallback_payload
    return {"risks": []}


def _salvage_risk_items(text: str) -> list[dict[str, Any]]:
    """当外层 `risks` JSON 损坏时，尽力抢救数组内对象。"""

    marker = '"risks"'
    marker_index = text.find(marker)
    if marker_index < 0:
        return []
    array_start = text.find("[", marker_index)
    if array_start < 0:
        return []

    decoder = json.JSONDecoder()
    risks: list[dict[str, Any]] = []
    depth = 0
    object_start: int | None = None
    for index in range(array_start, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
            continue
        if char == "]":
            if object_start is None and depth == 1:
                break
            depth = max(depth - 1, 0)
            continue
        if char == "{" and depth >= 1:
            if object_start is None:
                object_start = index
            continue
        if char == "}" and object_start is not None:
            candidate = text[object_start : index + 1]
            try:
                payload, _ = decoder.raw_decode(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                risks.append(payload)
            object_start = None
    return risks


def _normalize_risk_level(value: str) -> str:
    # 将中英文、别名、模糊表述统一映射到 missing/high/low。
    normalized = value.strip().lower()
    aliases = {
        "缺失": "missing",
        "信息缺失风险": "missing",
        "missing": "missing",
        "high": "high",
        "高": "high",
        "高风险": "high",
        "low": "low",
        "低": "low",
        "低风险": "low",
        "medium": "low",
        "中": "low",
        "中风险": "low",
    }
    if normalized in aliases:
        return aliases[normalized]
    if "缺失" in normalized or "空白" in normalized or "未约定" in normalized:
        return "missing"
    if "高" in normalized or "重大" in normalized:
        return "high"
    if "低" in normalized or "中" in normalized:
        return "low"
    return "high"


def _iter_nodes(nodes: list[ClauseNode]) -> list[ClauseNode]:
    ordered: list[ClauseNode] = []
    for node in nodes:
        ordered.append(node)
        ordered.extend(_iter_nodes(node.children))
    return ordered


def _locate_target_clause_id(task: ClauseReviewTask, clause_tree: list[ClauseNode], candidate_id: str) -> str:
    if candidate_id and (candidate_id == task.parent_clause_id or candidate_id in set(task.child_clause_ids)):
        return candidate_id
    for node in _iter_nodes(clause_tree):
        if node.heading == candidate_id:
            return node.node_id
    return task.parent_clause_id


def parse_clause_review_result(
    task: ClauseReviewTask,
    contract_id: str,
    clause_tree: list[ClauseNode],
    raw_text: str,
) -> ClauseReviewResult:
    """将单个父条款审查响应解析为结构化风险。"""

    payload = _extract_json_payload(raw_text)
    risks_payload = payload.get("risks", [])
    if not isinstance(risks_payload, list):
        risks_payload = []

    risks: list[ClauseRisk] = []
    for index, item in enumerate(risks_payload, start=1):
        if not isinstance(item, dict):
            continue
        risk = ClauseRisk(
            risk_id=f"{task.task_id}_risk_{index:03d}",
            contract_id=contract_id,
            parent_clause_id=task.parent_clause_id,
            target_clause_id=_locate_target_clause_id(task, clause_tree, str(item.get("target_clause_id", "")).strip()),
            target_text=str(item.get("target_text", "")).strip(),
            risk_title=str(item.get("risk_title", "")).strip(),
            risk_level=_normalize_risk_level(str(item.get("risk_level", "") or "medium")),
            risk_type=str(item.get("risk_type", "")).strip() or "其他",
            explanation=str(item.get("explanation", "")).strip(),
            suggestion=str(item.get("suggestion", "")).strip(),
            evidence_source=str(item.get("evidence_source", "")).strip() or task.parent_heading,
            source_excerpt=raw_text[:240].strip(),
        )
        if any([risk.target_text, risk.risk_title, risk.explanation, risk.suggestion]):
            # 至少有一个核心字段时才保留，避免空壳风险污染统计。
            risks.append(risk)

    return ClauseReviewResult(
        task_id=task.task_id,
        contract_id=contract_id,
        parent_clause_id=task.parent_clause_id,
        parent_heading=task.parent_heading,
        raw_response_excerpt=raw_text[:240].strip(),
        risks=risks,
    )


def _run_one_clause_task(
    task: ClauseReviewTask,
    contract_id: str,
    clause_tree: list[ClauseNode],
    background_brief: ContractBackgroundBrief,
    runtime: RuntimeConfig,
    prompt_context: ReviewPromptContext,
    *,
    raw_dir: Path,
    debug_dir: Path,
    reuse_raw_response: bool,
    log_callback: Any | None = None,
) -> ClauseReviewResult:
    safe_task_id = safe_filename(task.task_id)
    raw_path = raw_dir / f"{safe_task_id}.txt"
    debug_path = debug_dir / f"{safe_task_id}.request.json"
    if log_callback is not None:
        log_callback(f"CRSv1：开始审查父条款：{task.parent_heading}")
    if reuse_raw_response and raw_path.exists():
        raw_text = raw_path.read_text(encoding="utf-8")
    else:
        messages = build_clause_review_messages(background_brief, task, prompt_context)
        _write_debug_request(debug_path, runtime, messages, "clause_review")
        raw_text = send_chat(runtime, messages)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_text, encoding="utf-8")
    result = parse_clause_review_result(task, contract_id, clause_tree, raw_text)
    result.raw_response_path = str(raw_path)
    if log_callback is not None:
        log_callback(f"CRSv1：完成父条款审查：{task.parent_heading}，风险点 {len(result.risks)}")
    return result


def run_clause_review_tasks(
    contract_id: str,
    clause_tree: list[ClauseNode],
    tasks: list[ClauseReviewTask],
    background_brief: ContractBackgroundBrief,
    runtime: RuntimeConfig,
    prompt_context: ReviewPromptContext,
    *,
    raw_dir: Path,
    debug_dir: Path,
    reuse_raw_response: bool = False,
    max_workers: int = 1,
    progress_callback: Any | None = None,
    log_callback: Any | None = None,
) -> list[ClauseReviewResult]:
    """执行父条款审查任务，支持串行或线程池并发。"""

    if max_workers <= 1 or len(tasks) <= 1:
        # 小批量或单线程模式：按原始任务顺序执行。
        results: list[ClauseReviewResult] = []
        total = max(len(tasks), 1)
        for index, task in enumerate(tasks, start=1):
            if progress_callback is not None:
                progress_callback(index, total, task.parent_heading)
            results.append(
                _run_one_clause_task(
                    task,
                    contract_id,
                    clause_tree,
                    background_brief,
                    runtime,
                    prompt_context,
                    raw_dir=raw_dir,
                    debug_dir=debug_dir,
                    reuse_raw_response=reuse_raw_response,
                    log_callback=log_callback,
                )
            )
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(
                _run_one_clause_task,
                task,
                contract_id,
                clause_tree,
                background_brief,
                runtime,
                prompt_context,
                raw_dir=raw_dir,
                debug_dir=debug_dir,
                reuse_raw_response=reuse_raw_response,
                log_callback=log_callback,
            ): index
            for index, task in enumerate(tasks, start=1)
        }
        ordered_results: list[ClauseReviewResult | None] = [None] * len(tasks)
        total = max(len(tasks), 1)
        completed = 0
        for future in as_completed(future_to_index):
            # 并发完成顺序不稳定，这里再写回原索引，保证结果顺序稳定。
            index = future_to_index[future]
            result = future.result()
            ordered_results[index - 1] = result
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total, result.parent_heading)
        return [result for result in ordered_results if result is not None]
