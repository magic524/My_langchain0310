"""Production pipeline: doc/docx/pdf -> word2md -> CRSv1 -> comment docs/report."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from Contract_Review_System.core.v1.src.crsv1.pipeline import run_crsv1_prediction
from Contract_Review_System.common.local_llm_client import RuntimeConfig
from Contract_Review_System.word2md.src.word2md.common import collect_sources, resolve_path
from Contract_Review_System.word2md.src.word2md.pipeline import run_batch


ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_log(log_path: Path, message: str, *, log_callback: LogCallback | None = None) -> str:
    timestamp = datetime.now().strftime("%H:%M:%S")
    rendered = f"{timestamp} {message}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{rendered}\n")
    if log_callback is not None:
        log_callback(rendered)
    return rendered


def _report_progress(progress_callback: ProgressCallback | None, value: int, message: str) -> None:
    if progress_callback is not None:
        progress_callback(value, message)


def _sanitize_output_name(value: str) -> str:
    cleaned = "".join(char if char not in '<>:"/\\|?*' else "_" for char in value).strip().rstrip(".")
    return cleaned or "output"


def _make_unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    index = 2
    while True:
        candidate = target.with_name(f"{target.stem}_{index}{target.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _write_artifact_guide(artifact_dir: Path) -> Path:
    guide_path = artifact_dir / "文件说明.md"
    guide_path.write_text(
        "\n".join(
            [
                "# 辅助文件说明",
                "",
                "- `pipeline_summary.json`：本次生产流水线摘要。",
                "- `pipeline.log`：运行日志。",
                "- `crsv1_bundle/`：CRSv1 结构化结果、原始模型输出、调试请求和内部 JSON 产物。",
                "",
                "顶层主交付：",
                "",
                "- `*_CRSv1批注版.docx`：带批注的合同 Word。",
                "- `审查报告.docx`：首份合同的审查意见书。",
                "- `合同背景摘要.txt`：整份合同背景摘要。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return guide_path


def _resolve_input_mode(input_value: str) -> tuple[str | None, str | None]:
    resolved = resolve_path(input_value)
    if resolved.is_file():
        return str(resolved), None
    return None, str(resolved)


def _promote_primary_outputs(
    pipeline_output_dir: Path,
    primary_comment_file: str,
    primary_report_path: str,
    primary_background_brief_path: str,
) -> tuple[str, str, str]:
    promoted_comment = ""
    promoted_report = ""
    promoted_background = ""

    if primary_comment_file:
        comment_path = Path(primary_comment_file)
        if comment_path.exists():
            target = _make_unique_path(pipeline_output_dir / _sanitize_output_name(comment_path.name))
            shutil.copy2(comment_path, target)
            promoted_comment = str(target)

    if primary_report_path:
        report_path = Path(primary_report_path)
        if report_path.exists():
            target = _make_unique_path(pipeline_output_dir / _sanitize_output_name(report_path.name))
            shutil.copy2(report_path, target)
            promoted_report = str(target)

    if primary_background_brief_path:
        background_path = Path(primary_background_brief_path)
        if background_path.exists():
            target = _make_unique_path(pipeline_output_dir / "合同背景摘要.txt")
            shutil.copy2(background_path, target)
            promoted_background = str(target)

    return promoted_comment, promoted_report, promoted_background


def run_contract_review_pipeline(
    *,
    input_value: str,
    run_name: str,
    runtime: RuntimeConfig,
    pipeline_output_dir: Path,
    word2md_output_root: Path,
    recursive: bool = False,
    device: str = "cpu",
    reuse_raw_responses: bool = False,
    review_stance: str | None = None,
    extra_user_instruction: str = "",
    display_risk_levels: list[str] | None = None,
    max_workers: int | None = None,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> dict[str, str]:
    """Run the production review pipeline and write all output artifacts."""

    pipeline_output_dir = pipeline_output_dir.resolve()
    pipeline_output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = pipeline_output_dir / "_artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    crsv1_output_dir = artifact_dir / "crsv1_bundle"
    log_path = artifact_dir / "pipeline.log"
    summary_path = artifact_dir / "pipeline_summary.json"

    _report_progress(progress_callback, 5, "阶段：输入校验")
    _append_log(log_path, f"任务开始：{run_name}", log_callback=log_callback)
    _append_log(log_path, f"输入文件：{resolve_path(input_value)}", log_callback=log_callback)
    _append_log(log_path, f"审查立场：{(review_stance or '').strip().lower() or 'default'}", log_callback=log_callback)
    _append_log(log_path, f"用户补充提示：{'已填写' if extra_user_instruction.strip() else '未填写'}", log_callback=log_callback)
    _append_log(log_path, f"展示风险等级：{','.join(display_risk_levels or ['missing', 'high', 'low'])}", log_callback=log_callback)
    _append_log(log_path, f"模型请求超时：{runtime.request_timeout_seconds} 秒/次", log_callback=log_callback)
    if max_workers is None:
        _append_log(log_path, "父条款并行审查数：自动（按每份合同的条款数）", log_callback=log_callback)
    else:
        _append_log(log_path, f"父条款并行审查数：{max(1, int(max_workers))}", log_callback=log_callback)

    input_file, input_dir = _resolve_input_mode(input_value)
    items = collect_sources(input_file, input_dir, recursive)
    _append_log(log_path, f"待处理合同数：{len(items)}", log_callback=log_callback)

    _report_progress(progress_callback, 10, "阶段：格式转换")
    _append_log(log_path, "阶段开始：格式转换(word2md)", log_callback=log_callback)
    results, word2md_summary_path = run_batch(
        items,
        run_name,
        word2md_output_root.resolve(),
        device,
        False,
        [word2md_output_root.resolve()],
    )
    _append_log(log_path, f"word2md 摘要：{word2md_summary_path}", log_callback=log_callback)

    successful_results = [result for result in results if result.get("status") == "ok"]
    failed_results = [result for result in results if result.get("status") != "ok"]
    for failed in failed_results:
        _append_log(log_path, f"word2md 失败：{failed.get('sample_id', '')} {failed.get('reason', '')}", log_callback=log_callback)
    if not successful_results:
        msg = str(failed_results[0].get("error_detail", "")).strip() if failed_results else ""
        raise RuntimeError(msg or "No successful word2md outputs were produced.")

    _report_progress(progress_callback, 30, "阶段：合同背景摘要 / 条款切分 / 多条款审查")
    _append_log(log_path, "阶段开始：CRSv1", log_callback=log_callback)
    crsv1_result = run_crsv1_prediction(
        run_name,
        runtime,
        output_dir=crsv1_output_dir,
        word2md_run_root=word2md_summary_path.parent,
        reuse_raw_responses=reuse_raw_responses,
        review_stance=review_stance,
        extra_user_instruction=extra_user_instruction,
        display_risk_levels=display_risk_levels,
        max_workers=max_workers,
        progress_callback=(
            (lambda value, message: _report_progress(progress_callback, min(95, max(30, value)), message))
            if progress_callback is not None
            else None
        ),
        log_callback=(
            (lambda message: _append_log(log_path, message, log_callback=log_callback))
            if log_callback is not None
            else (lambda message: _append_log(log_path, message))
        ),
    )
    _append_log(log_path, f"CRSv1 结果：{crsv1_result['result_path']}", log_callback=log_callback)

    _report_progress(progress_callback, 96, "阶段：输出整理")
    primary_comment_file, primary_report_path, primary_background_brief_path = _promote_primary_outputs(
        pipeline_output_dir,
        crsv1_result.get("primary_comment_file", ""),
        crsv1_result.get("primary_report_path", ""),
        crsv1_result.get("primary_background_brief_path", ""),
    )
    if primary_comment_file:
        _append_log(log_path, f"批注版 Word：{primary_comment_file}", log_callback=log_callback)
    if primary_report_path:
        _append_log(log_path, f"审查报告：{primary_report_path}", log_callback=log_callback)
    if primary_background_brief_path:
        _append_log(log_path, f"合同背景摘要：{primary_background_brief_path}", log_callback=log_callback)

    guide_path = _write_artifact_guide(artifact_dir)
    summary_payload = {
        "run_name": run_name,
        "generated_at": datetime.now().isoformat(),
        "pipeline_output_dir": str(pipeline_output_dir),
        "word2md_run_root": str(word2md_summary_path.parent),
        "word2md_summary_path": str(word2md_summary_path),
        "crsv1_output_dir": crsv1_result["output_dir"],
        "crsv1_result_path": crsv1_result["result_path"],
        "crsv1_summary_path": crsv1_result["summary_path"],
        "statistics_path": crsv1_result["statistics_path"],
        "comment_output_dir": crsv1_result["comment_output_dir"],
        "primary_comment_file": primary_comment_file,
        "primary_report_path": primary_report_path,
        "primary_background_brief_path": primary_background_brief_path,
        "log_path": str(log_path),
        "artifact_dir": str(artifact_dir),
        "successful_contracts": len(successful_results),
        "failed_contracts": len(failed_results),
        "review_stance": (review_stance or "").strip().lower(),
        "extra_user_instruction": extra_user_instruction.strip(),
        "display_risk_levels": list(display_risk_levels or ["missing", "high", "low"]),
    }
    _write_json(summary_path, summary_payload)
    _report_progress(progress_callback, 100, "阶段：完成")
    _append_log(log_path, f"任务完成：{summary_path}", log_callback=log_callback)

    return {
        "pipeline_output_dir": str(pipeline_output_dir),
        "crsv1_result_path": crsv1_result["result_path"],
        "comment_output_dir": crsv1_result["comment_output_dir"],
        "summary_path": str(summary_path),
        "log_path": str(log_path),
        "artifact_guide_path": str(guide_path),
        "primary_comment_file": primary_comment_file,
        "primary_report_path": primary_report_path,
        "primary_background_brief_path": primary_background_brief_path,
    }
