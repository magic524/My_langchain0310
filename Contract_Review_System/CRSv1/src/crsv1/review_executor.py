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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_debug_request(path: Path, runtime: RuntimeConfig, messages: list[tuple[str, str]], note: str) -> None:
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
    """Send a chat request through the shared local LLM HTTP layer."""

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
    """Generate a contract-level background brief."""

    safe_contract_id = safe_filename(contract_id)
    raw_path = raw_dir / f"{safe_contract_id}.background.txt"
    debug_path = debug_dir / f"{safe_contract_id}.background.request.json"
    if log_callback is not None:
        log_callback(f"CRSv1：开始生成合同背景摘要：{contract_id}")
    if reuse_raw_response and raw_path.exists():
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
    """Best-effort recovery when the outer `risks` JSON is malformed."""

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
    normalized = value.strip().lower()
    if normalized not in {"high", "medium", "low"}:
        return "medium"
    return normalized


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
    """Parse one parent-clause review result into structured risks."""

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
    """Run review tasks through a serial-or-threaded interface."""

    if max_workers <= 1 or len(tasks) <= 1:
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
            index = future_to_index[future]
            result = future.result()
            ordered_results[index - 1] = result
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total, result.parent_heading)
        return [result for result in ordered_results if result is not None]
