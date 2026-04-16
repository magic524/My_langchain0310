from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from Contract_Review_System.common.local_llm_client import RuntimeConfig

from .clause_tree_parser import build_review_tasks, parse_clause_tree
from .input_adapter import load_contract_bundles
from .report_export import export_contract_report
from .review_executor import run_background_brief, run_clause_review_tasks
from .risk_assembler import (
    aggregate_clause_risks,
    build_risk_statistics,
    filter_risks_by_level,
    normalize_display_risk_levels,
)
from .runtime_types import CRSv1ResultPayload, ContractReviewResult, ReviewPromptContext
from .word_comment_export import export_contract_comment_doc


CURRENT_FILE = Path(__file__).resolve()
CRSV1_SRC_ROOT = CURRENT_FILE.parents[1]
CRSV1_ROOT = CRSV1_SRC_ROOT.parent.parent

ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    # 统一 JSON 写盘入口，确保目录存在且 UTF-8 编码。
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_crsv1_review_for_result(
    contract_id: str,
    markdown_text: str,
    source_files: dict[str, str],
    runtime: RuntimeConfig,
    *,
    output_dir: Path,
    review_stance: str | None = None,
    extra_user_instruction: str = "",
    display_risk_levels: list[str] | None = None,
    reuse_raw_responses: bool = False,
    max_workers: int | None = None,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> ContractReviewResult:
    """对单份合同执行 CRSv1 全流程并返回结构化结果。"""

    prompt_context = ReviewPromptContext(
        review_stance=(review_stance or "").strip().lower(),
        extra_user_instruction=extra_user_instruction.strip(),
        display_risk_levels=normalize_display_risk_levels(display_risk_levels),
    )
    raw_dir = output_dir / "raw_responses"
    debug_dir = output_dir / "debug_requests"
    raw_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    if log_callback is not None:
        log_callback(f"CRSv1：开始条款切分：{contract_id}")
    # 第一步：将合同切分为条款树，并以父条款构造审查任务。
    clause_tree = parse_clause_tree(contract_id, markdown_text)
    tasks = build_review_tasks(contract_id, clause_tree)
    if log_callback is not None:
        log_callback(f"CRSv1：条款切分完成：{contract_id}，父条款 {len(tasks)} 个")
    resolved_max_workers = max(1, int(max_workers)) if max_workers is not None else max(1, len(tasks))
    if progress_callback is not None:
        progress_callback(40, "CRSv1：生成合同背景摘要")
    # 第二步：先抽取全局背景，后续每个父条款审查都复用这份上下文。
    background_brief, background_raw_path = run_background_brief(
        contract_id,
        markdown_text,
        runtime,
        prompt_context,
        raw_dir=raw_dir,
        debug_dir=debug_dir,
        reuse_raw_response=reuse_raw_responses,
        log_callback=log_callback,
    )
    if progress_callback is not None:
        progress_callback(50, "CRSv1：按父条款执行审查")
    # 第三步：逐个父条款审查，可按 max_workers 并发执行。
    clause_reviews = run_clause_review_tasks(
        contract_id,
        clause_tree,
        tasks,
        background_brief,
        runtime,
        prompt_context,
        raw_dir=raw_dir,
        debug_dir=debug_dir,
        reuse_raw_response=reuse_raw_responses,
        max_workers=resolved_max_workers,
        progress_callback=(
            (lambda index, total, heading: progress_callback(50 + int(index / max(total, 1) * 20), f"CRSv1：多条款审查 {index}/{total} - {heading}"))
            if progress_callback is not None
            else None
        ),
        log_callback=log_callback,
    )
    if progress_callback is not None:
        progress_callback(75, "CRSv1：组装风险结果")
    if log_callback is not None:
        log_callback(f"CRSv1：开始风险组装：{contract_id}")
    # 第四步：跨父条款去重聚合，并按展示级别过滤后统计。
    aggregated_risks = aggregate_clause_risks(clause_reviews)
    selected_risks = filter_risks_by_level(aggregated_risks, prompt_context.display_risk_levels)
    risk_statistics = build_risk_statistics(selected_risks)
    if log_callback is not None:
        log_callback(f"CRSv1：风险组装完成：{contract_id}，聚合风险 {len(aggregated_risks)} 个")
    return ContractReviewResult(
        contract_id=contract_id,
        source_files=source_files,
        review_context=prompt_context,
        background_brief=background_brief,
        clause_tree=clause_tree,
        clause_reviews=clause_reviews,
        aggregated_risks=aggregated_risks,
        risk_statistics=risk_statistics,
        report_summary={
            "background_raw_path": background_raw_path,
            "task_count": len(tasks),
            "clause_review_count": len(clause_reviews),
            "selected_risks": selected_risks,
            "selected_statistics": risk_statistics,
        },
    )


def run_crsv1_prediction(
    run_id: str,
    runtime: RuntimeConfig,
    *,
    output_dir: Path,
    word2md_run_root: Path | None = None,
    reuse_raw_responses: bool = False,
    contract_filter: str | None = None,
    review_stance: str | None = None,
    extra_user_instruction: str = "",
    display_risk_levels: list[str] | None = None,
    max_workers: int | None = None,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> dict[str, str]:
    """对一个 word2md 批次执行 CRSv1，并导出结果文件。"""

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bundles, warnings, resolved_run_root = load_contract_bundles(run_id, run_root=word2md_run_root)
    if contract_filter:
        bundles = [bundle for bundle in bundles if contract_filter in bundle.contract_id]
        if not bundles:
            msg = f"未找到匹配合同：{contract_filter}"
            raise RuntimeError(msg)

    contracts: list[ContractReviewResult] = []
    # 合同批注版会单独集中输出，便于用户直接查看修改建议。
    comment_output_dir = output_dir / "原合同批注版_CRSv1"
    comment_output_dir.mkdir(parents=True, exist_ok=True)
    contract_output_root = output_dir / "contracts"
    contract_output_root.mkdir(parents=True, exist_ok=True)
    comment_contracts: list[dict[str, Any]] = []
    report_paths: list[str] = []
    background_brief_paths: list[str] = []

    for bundle in bundles:
        contract_output_dir = contract_output_root / bundle.contract_id.replace("/", "_").replace("\\", "_")
        contract_output_dir.mkdir(parents=True, exist_ok=True)
        if progress_callback is not None:
            progress_callback(35, f"CRSv1：准备审查 {bundle.contract_id}")
        contract_result = run_crsv1_review_for_result(
            bundle.contract_id,
            bundle.markdown_text,
            bundle.source_files,
            runtime,
            output_dir=contract_output_dir,
            review_stance=review_stance,
            extra_user_instruction=extra_user_instruction,
            display_risk_levels=display_risk_levels,
            reuse_raw_responses=reuse_raw_responses,
            max_workers=max_workers,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
        if progress_callback is not None:
            progress_callback(80, f"CRSv1：导出审查报告 {bundle.contract_id}")
        if log_callback is not None:
            log_callback(f"CRSv1：开始导出审查报告：{bundle.contract_id}")
        report_export_result = export_contract_report(contract_result, contract_output_dir)
        if log_callback is not None:
            log_callback(f"CRSv1：审查报告导出完成：{report_export_result['report_docx_path']}")
        report_paths.append(report_export_result["report_docx_path"])
        background_brief_paths.append(report_export_result["background_brief_text_path"])
        if progress_callback is not None:
            progress_callback(88, f"CRSv1：导出批注版 Word {bundle.contract_id}")
        if log_callback is not None:
            log_callback(f"CRSv1：开始导出批注版 Word：{bundle.contract_id}")
        comment_contracts.append(export_contract_comment_doc(contract_result, comment_output_dir))
        if log_callback is not None:
            log_callback(f"CRSv1：批注版 Word 导出完成：{bundle.contract_id}")
        contracts.append(contract_result)

    payload = CRSv1ResultPayload(
        meta={
            "generated_at": datetime.now().isoformat(),
            "run_id": run_id,
            "word2md_run_root": str(resolved_run_root),
            "contract_count": len(contracts),
            "review_stance": (review_stance or "").strip().lower(),
            "extra_user_instruction": extra_user_instruction.strip(),
            "display_risk_levels": normalize_display_risk_levels(display_risk_levels),
            "max_workers": max_workers if max_workers is not None else "auto",
        },
        warnings=warnings,
        contracts=contracts,
    )
    result_path = output_dir / "crsv1_result.json"
    # 结构化总结果：保留完整合同级结果（包含条款树/风险详情）。
    _write_json(
        result_path,
        {
            "meta": payload.meta,
            "warnings": payload.warnings,
            "contracts": [asdict(contract) for contract in payload.contracts],
        },
    )
    statistics_path = output_dir / "risk_statistics.json"
    # 统计汇总：方便前端或脚本直接读取统计面板。
    _write_json(
        statistics_path,
        {
            "generated_at": datetime.now().isoformat(),
            "contracts": [
                {"contract_id": contract.contract_id, "risk_statistics": contract.risk_statistics}
                for contract in contracts
            ],
        },
    )
    summary_path = output_dir / "review_summary.json"
    # 轻量摘要：记录关键输出路径与主入口文件。
    _write_json(
        summary_path,
        {
            "generated_at": datetime.now().isoformat(),
            "result_path": str(result_path),
            "comment_output_dir": str(comment_output_dir),
            "contracts": comment_contracts,
            "report_paths": report_paths,
            "background_brief_paths": background_brief_paths,
        },
    )

    primary_comment_file = comment_contracts[0]["output_docx"] if comment_contracts else ""
    primary_report_path = report_paths[0] if report_paths else ""
    primary_background_brief_path = background_brief_paths[0] if background_brief_paths else ""
    if progress_callback is not None:
        progress_callback(92, "CRSv1：写出结构化结果")
    return {
        "output_dir": str(output_dir),
        "result_path": str(result_path),
        "statistics_path": str(statistics_path),
        "summary_path": str(summary_path),
        "comment_output_dir": str(comment_output_dir),
        "primary_comment_file": primary_comment_file,
        "primary_report_path": primary_report_path,
        "primary_background_brief_path": primary_background_brief_path,
    }
