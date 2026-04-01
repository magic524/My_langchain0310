"""Production pipeline: doc/docx -> word2md -> local_llm_result -> comment docs."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from Contract_Review_System.common.local_llm_client import RuntimeConfig
from Contract_Review_System.only_prompt_local_llm.src.only_prompt_local_llm.local_model_runner import (
    build_local_llm_contract_result,
    run_local_review_on_markdown,
)
from Contract_Review_System.only_prompt_local_llm.src.only_prompt_local_llm.word_comment_export import (
    export_local_llm_comment_docs,
)
from Contract_Review_System.word2md.src.word2md.common import collect_sources, resolve_path
from Contract_Review_System.word2md.src.word2md.pipeline import run_batch


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"JSON root must be an object: {path}"
        raise ValueError(msg)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_log(log_path: Path, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def _sanitize_output_name(value: str) -> str:
    """Return a filesystem-safe display name."""

    cleaned = "".join(char if char not in '<>:"/\\|?*' else "_" for char in value).strip().rstrip(".")
    return cleaned or "output"


def _make_unique_path(target: Path) -> Path:
    """Append a numeric suffix when the target path already exists."""

    if not target.exists():
        return target

    index = 2
    while True:
        candidate = target.with_name(f"{target.stem}_{index}{target.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _write_artifact_guide(artifact_dir: Path) -> Path:
    """Write a short guide for auxiliary pipeline artifacts."""

    guide_path = artifact_dir / "文件说明.md"
    guide_path.write_text(
        "\n".join(
            [
                "# 辅助文件说明",
                "",
                "这个目录存放合同审查流水线的辅助产物，便于排错、复盘和后续评测，不是最终交付主结果。",
                "",
                "## 文件与作用",
                "",
                "- `pipeline_summary.json`：整次流水线的运行摘要，包括输入、输出位置、成功失败数量和 warning。",
                "- `pipeline.log`：流水线运行日志，排查报错时优先查看。",
                "- `local_llm_predictions.json`：精简版 local LLM 风险列表，便于快速浏览或兼容旧脚本。",
                "- `raw_responses/`：模型原始返回文本，用于检查模型是否按要求输出 JSON。",
                "- `debug_requests/`：发送给模型的调试请求信息，用于排查 prompt、请求体和配置问题。",
                "- `批注导出结果.json`：批注版 Word 导出明细，记录每个风险点锚定到原文的位置。",
                "- `批注导出结果.md`：上述导出明细的 Markdown 阅读版。",
                "",
                "## 顶层主结果",
                "",
                "- 上一级目录中的 `local_llm_result.json`：本次审查的主结果文件。",
                "- 上一级目录中的 `*_批注版.docx`：最终可直接查看的批注版 Word 文件，默认跟输入文件名对应。",
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


def _build_contract_result(
    result: dict[str, Any],
    runtime: RuntimeConfig,
    *,
    raw_dir: Path,
    debug_dir: Path,
    reuse_raw_responses: bool,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    contract_id = str(result.get("sample_id", "")).strip()
    markdown_path = Path(str(result.get("output_md", ""))).resolve()
    if not contract_id or not markdown_path.exists():
        msg = f"Missing successful word2md output for sample: {contract_id or '<empty>'}"
        raise FileNotFoundError(msg)

    meta_path = markdown_path.with_name("meta.json")
    meta_payload = _read_json(meta_path)
    source_path = str(meta_payload.get("source_path", "")).strip()
    if not source_path:
        warnings.append(f"{contract_id}: source_path missing in meta.json")

    markdown_text = markdown_path.read_text(encoding="utf-8")
    safe_contract_id = contract_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    raw_path = raw_dir / f"{safe_contract_id}.txt"
    debug_path = debug_dir / f"{safe_contract_id}.request.json"
    risks, _ = run_local_review_on_markdown(
        contract_id,
        markdown_text,
        runtime,
        raw_path=raw_path,
        debug_path=debug_path,
        reuse_raw_response=reuse_raw_responses,
    )

    contract_result = build_local_llm_contract_result(
        contract_id,
        markdown_text,
        {
            "original_doc": source_path,
            "original_md": str(markdown_path),
            "meta_path": str(meta_path),
        },
        risks,
        raw_response_path=str(raw_path),
    )
    return {
        "contract": {
            "contract_id": contract_result.contract_id,
            "source_files": contract_result.source_files,
            "full_contract_text": contract_result.full_contract_text,
            "clauses": [asdict(item) for item in contract_result.clauses],
            "local_llm_risks": [asdict(item) for item in contract_result.local_llm_risks],
            "raw_response_path": contract_result.raw_response_path,
        },
        "risk_count": len(contract_result.local_llm_risks),
    }, warnings


def _promote_comment_docs(
    pipeline_output_dir: Path,
    comment_summary: dict[str, Any],
    *,
    artifact_comment_dir: Path,
) -> list[str]:
    """Move exported comment docs to the top-level output directory."""

    promoted_paths: list[str] = []
    for contract_summary in comment_summary.get("contracts", []):
        if not isinstance(contract_summary, dict):
            continue
        source_docx = Path(str(contract_summary.get("source_docx", "")))
        exported_docx = Path(str(contract_summary.get("output_docx", "")))
        if not exported_docx.exists():
            continue

        preferred_name = _sanitize_output_name(f"{source_docx.stem}_批注版.docx")
        top_level_path = _make_unique_path(pipeline_output_dir / preferred_name)
        shutil.move(str(exported_docx), str(top_level_path))
        contract_summary["output_docx"] = str(top_level_path)
        promoted_paths.append(str(top_level_path))

    detail_json = artifact_comment_dir / "批注导出结果.json"
    detail_md = artifact_comment_dir / "批注导出结果.md"
    if detail_json.exists():
        comment_summary["detail_json_path"] = str(detail_json)
    if detail_md.exists():
        comment_summary["detail_markdown_path"] = str(detail_md)
    return promoted_paths


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
) -> dict[str, str]:
    """Run the production review pipeline and write all output artifacts."""

    pipeline_output_dir = pipeline_output_dir.resolve()
    pipeline_output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = pipeline_output_dir / "_artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifact_dir / "pipeline.log"

    _append_log(log_path, f"run started: {run_name}")
    _append_log(log_path, f"input: {input_value}")

    input_file, input_dir = _resolve_input_mode(input_value)
    items = collect_sources(input_file, input_dir, recursive)
    _append_log(log_path, f"word2md items: {len(items)}")

    results, word2md_summary_path = run_batch(
        items,
        run_name,
        word2md_output_root.resolve(),
        device,
        False,
        [word2md_output_root.resolve()],
    )
    _append_log(log_path, f"word2md summary: {word2md_summary_path}")

    successful_results = [result for result in results if result.get("status") == "ok"]
    failed_results = [result for result in results if result.get("status") != "ok"]
    for failed in failed_results:
        _append_log(log_path, f"word2md failed: {failed.get('sample_id', '')} {failed.get('reason', '')}")
    if not successful_results:
        msg = "No successful word2md outputs were produced."
        raise RuntimeError(msg)

    raw_dir = artifact_dir / "raw_responses"
    debug_dir = artifact_dir / "debug_requests"
    warnings: list[str] = []
    contracts: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    for result in successful_results:
        contract_payload, contract_warnings = _build_contract_result(
            result,
            runtime,
            raw_dir=raw_dir,
            debug_dir=debug_dir,
            reuse_raw_responses=reuse_raw_responses,
        )
        warnings.extend(contract_warnings)
        contracts.append(contract_payload["contract"])
        prediction_rows.append(
            {
                "contract_id": contract_payload["contract"]["contract_id"],
                "risk_count": contract_payload["risk_count"],
                "risks": contract_payload["contract"]["local_llm_risks"],
            }
        )
        _append_log(
            log_path,
            f"local llm completed: {contract_payload['contract']['contract_id']} risks={contract_payload['risk_count']}",
        )

    local_llm_result_payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "run_name": run_name,
            "input": str(resolve_path(input_value)),
            "word2md_run_root": str(word2md_summary_path.parent),
            "word2md_summary_path": str(word2md_summary_path),
            "contract_count": len(contracts),
        },
        "warnings": warnings,
        "contracts": contracts,
    }
    local_llm_result_path = pipeline_output_dir / "local_llm_result.json"
    _write_json(local_llm_result_path, local_llm_result_payload)

    prediction_path = artifact_dir / "local_llm_predictions.json"
    prediction_path.write_text(
        json.dumps(prediction_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    artifact_comment_dir = artifact_dir / "comment_export"
    comment_summary = export_local_llm_comment_docs(local_llm_result_path, artifact_comment_dir)
    promoted_comment_files = _promote_comment_docs(
        pipeline_output_dir,
        comment_summary,
        artifact_comment_dir=artifact_comment_dir,
    )
    _append_log(log_path, f"comment export detail: {artifact_comment_dir}")

    summary_payload = {
        "run_name": run_name,
        "generated_at": datetime.now().isoformat(),
        "pipeline_output_dir": str(pipeline_output_dir),
        "word2md_run_root": str(word2md_summary_path.parent),
        "word2md_summary_path": str(word2md_summary_path),
        "local_llm_result_path": str(local_llm_result_path),
        "prediction_path": str(prediction_path),
        "comment_output_dir": str(pipeline_output_dir),
        "comment_files": promoted_comment_files,
        "log_path": str(log_path),
        "artifact_dir": str(artifact_dir),
        "successful_contracts": len(successful_results),
        "failed_contracts": len(failed_results),
        "warnings": warnings,
    }
    summary_path = artifact_dir / "pipeline_summary.json"
    _write_json(summary_path, summary_payload)
    guide_path = _write_artifact_guide(artifact_dir)
    _append_log(log_path, f"run completed: {summary_path}")

    return {
        "pipeline_output_dir": str(pipeline_output_dir),
        "local_llm_result_path": str(local_llm_result_path),
        "prediction_path": str(prediction_path),
        "comment_output_dir": str(pipeline_output_dir),
        "summary_path": str(summary_path),
        "log_path": str(log_path),
        "artifact_guide_path": str(guide_path),
    }
