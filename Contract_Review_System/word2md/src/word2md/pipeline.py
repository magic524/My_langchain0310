"""word2md pipeline: normalize contract files into Markdown plus metadata."""

from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import REPO_ROOT, SourceItem
from .docx_features import (
    extract_docx_comments_with_anchors,
    extract_docx_style_hints,
    extract_docx_visible_paragraphs,
)
from .mammoth_converter import convert_docx_to_markdown, is_mammoth_available
from .markdown_formatter import inject_inline_annotations, postprocess_legal_markdown, repair_missing_numbered_paragraphs
from .word_processing import convert_doc_to_docx, convert_pdf_to_docx, prepare_docx_for_docling


MODEL_CACHE_ROOT = REPO_ROOT / "data" / "contract_review_runtime_cache"
SUPPORTED_MARKDOWN_BACKENDS = {"auto", "mammoth", "docling"}


def configure_restricted_runtime() -> None:
    """Use workspace-local Hugging Face caches for Docling runtime."""

    huggingface_root = MODEL_CACHE_ROOT / "huggingface"
    transformers_root = MODEL_CACHE_ROOT / "transformers"
    for cache_dir in (huggingface_root, transformers_root):
        cache_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HOME", str(huggingface_root))
    os.environ.setdefault("HF_HUB_CACHE", str(huggingface_root / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(huggingface_root / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(transformers_root))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def explain_docling_error(raw_error: str) -> str:
    """Convert low-level Docling errors into user-facing diagnostics."""

    lowered = raw_error.lower()
    if "winerror 1314" in lowered:
        return (
            "Docling 转换失败：当前设备限制了模型缓存所需的链接权限。"
            "如果持续失败，请检查公司安全策略是否拦截模型下载或缓存写入。"
        )
    if "huggingface" in lowered:
        return "Docling 转换失败：所需模型无法完成下载或缓存，请检查网络、代理或本地缓存目录权限。"
    return raw_error


def explain_mammoth_error(raw_error: str) -> str:
    """Convert low-level Mammoth errors into user-facing diagnostics."""

    if "无法导入 mammoth" in raw_error:
        return raw_error
    return f"Mammoth 转换失败：{raw_error}"


def resolve_markdown_backend(preferred_backend: str) -> str:
    """Resolve the actual backend used for DOCX to Markdown conversion."""

    normalized = preferred_backend.strip().lower() or "auto"
    if normalized not in SUPPORTED_MARKDOWN_BACKENDS:
        msg = f"不支持的 Markdown 后端：{preferred_backend}"
        raise ValueError(msg)

    if normalized == "auto":
        return "mammoth" if is_mammoth_available() else "docling"
    return normalized


def import_docling() -> tuple[type[Any], Any, type[Any]]:
    """Import Docling lazily with a friendly error message."""

    try:
        configure_restricted_runtime()
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter, WordFormatOption

        return DocumentConverter, InputFormat, WordFormatOption
    except ImportError as exc:
        raise RuntimeError(
            "无法导入 docling，请先进入 `langchain` 环境并安装依赖："
            "`conda activate langchain && pip install docling`"
        ) from exc


def run_docling(input_path: Path, *, file_type: str, device: str = "cpu") -> tuple[object | None, str]:
    """Execute Docling conversion."""

    del device

    try:
        DocumentConverter, InputFormat, WordFormatOption = import_docling()
        if file_type == "pdf":
            raise RuntimeError("PDF 需先转换为 DOCX 后再进入 Docling，当前链路不再支持 Docling 直接解析 PDF。")

        converter = DocumentConverter(
            format_options={
                InputFormat.DOCX: WordFormatOption(),
            }
        )
        result = converter.convert(str(input_path))
        return result.document, ""
    except Exception as exc:  # noqa: BLE001
        raw_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        return None, explain_docling_error(raw_error)


def export_markdown_from_docling(document: object, output_dir: Path, apply_postprocess: bool) -> tuple[str, str]:
    """Export a Docling document into `output.md`."""

    try:
        markdown = document.export_to_markdown(
            page_break_placeholder="\n\n---\n\n",
            mark_annotations=True,
        )
        if apply_postprocess:
            markdown = postprocess_legal_markdown(markdown)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "output.md").write_text(markdown, encoding="utf-8")
        return "ok", ""
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return "error", str(exc)


def export_markdown_from_mammoth(input_path: Path, output_dir: Path, apply_postprocess: bool) -> tuple[str, str]:
    """Export a DOCX file into `output.md` via Mammoth."""

    try:
        result = convert_docx_to_markdown(input_path)
        markdown = result.markdown
        if apply_postprocess:
            markdown = postprocess_legal_markdown(markdown)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "output.md").write_text(markdown, encoding="utf-8")
        return "ok", result.warning_text
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return "error", explain_mammoth_error(str(exc))


def write_meta(
    output_dir: Path,
    run_id: str,
    item: SourceItem,
    device: str,
    elapsed_seconds: float,
    doc_conversion: dict[str, Any] | None,
    docx_preprocess: dict[str, Any] | None,
    markdown_backend_requested: str,
    markdown_backend_used: str,
    md_status: str,
    md_error: str,
    backend_error: str,
    comment_anchors: list[dict[str, Any]],
    style_hints: list[dict[str, Any]],
    inline_stats: dict[str, int],
) -> None:
    """Write per-file metadata for review and debugging."""

    meta = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "sample_id": item.sample_id,
        "source_path": str(item.source_path),
        "file_type": item.file_type,
        "device": device,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "doc_conversion": doc_conversion,
        "docx_preprocess": docx_preprocess,
        "markdown_backend_requested": markdown_backend_requested,
        "markdown_backend_used": markdown_backend_used,
        "backend_error": backend_error,
        "docling_error": backend_error if markdown_backend_used == "docling" else "",
        "md_export": {"status": md_status, "error": md_error},
        "comment_anchor_count": len(comment_anchors),
        "comment_anchors": comment_anchors,
        "style_hint_count": len(style_hints),
        "style_hints": style_hints,
        "inline_injection": inline_stats,
        "output_md": str(output_dir / "output.md") if md_status == "ok" else "",
    }
    if docx_preprocess:
        fallback_pdf_parse = docx_preprocess.get("fallback_pdf_parse")
        if fallback_pdf_parse is not None:
            meta["fallback_pdf_parse"] = fallback_pdf_parse
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_conversion_failure_result(item: SourceItem, message: str) -> dict[str, Any]:
    """Build a normalized failure result for preprocessing errors."""

    return {
        "sample_id": item.sample_id,
        "source": str(item.source_path),
        "output_subdir": item.output_subdir.as_posix(),
        "status": "failed",
        "reason": message,
    }


def process_one(
    item: SourceItem,
    run_id: str,
    output_root: Path,
    device: str,
    no_postprocess: bool,
    history_output_roots: list[Path],
    *,
    markdown_backend: str = "auto",
) -> dict[str, Any]:
    """Convert a single contract file into Markdown plus metadata."""

    output_dir = output_root / run_id / item.output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 68}")
    print(f"样本: {item.sample_id}")
    print(f"源文件: {item.source_path}")
    print(f"{'=' * 68}")

    working_path = item.source_path
    actual_markdown_backend = resolve_markdown_backend(markdown_backend)
    doc_conversion_info: dict[str, Any] | None = None
    docx_preprocess_info: dict[str, Any] | None = None
    comment_anchors: list[dict[str, Any]] = []
    style_hints: list[dict[str, Any]] = []
    inline_stats: dict[str, int] = {
        "comment_matched": 0,
        "comment_unmatched": 0,
        "style_matched": 0,
        "style_unmatched": 0,
    }
    start_time = time.time()

    if item.file_type in {"doc", "pdf"}:
        source_label = ".doc" if item.file_type == "doc" else ".pdf"
        print(f"[预处理] 检测到 `{source_label}`，开始尝试转换为 `.docx` ...")
        conversion_start = time.time()
        if item.file_type == "doc":
            docx_path, method = convert_doc_to_docx(
                item.source_path,
                output_dir / "_converted",
                cache_roots=history_output_roots,
                output_subdir=item.output_subdir,
                current_run_id=run_id,
            )
        else:
            docx_path, method = convert_pdf_to_docx(
                item.source_path,
                output_dir / "_converted",
                cache_roots=history_output_roots,
                output_subdir=item.output_subdir,
                current_run_id=run_id,
            )
        conversion_elapsed = round(time.time() - conversion_start, 2)
        if docx_path is None:
            message = f"{item.file_type} 预处理失败，已跳过 Markdown 转换。"
            doc_conversion_info = {"success": False, "error": method}
            elapsed_seconds = round(time.time() - start_time, 2)
            write_meta(
                output_dir,
                run_id,
                item,
                device,
                elapsed_seconds,
                doc_conversion_info,
                docx_preprocess_info,
                markdown_backend,
                actual_markdown_backend,
                "error",
                "",
                message,
                comment_anchors,
                style_hints,
                inline_stats,
            )
            print(f"[失败] {message}")
            return _build_conversion_failure_result(item, message)

        doc_conversion_info = {
            "success": True,
            "method": method,
            "elapsed_seconds": conversion_elapsed,
            "output_path": str(docx_path),
            "source_file_type": item.file_type,
        }
        working_path = docx_path
        print(f"[预处理] 成功: {method}, {conversion_elapsed}s")

    conversion_input_path = working_path
    effective_file_type = item.file_type
    if working_path.suffix.lower() == ".docx" and actual_markdown_backend == "docling":
        conversion_input_path, docx_preprocess_info = prepare_docx_for_docling(
            working_path,
            output_dir / "_docling_input",
        )
        effective_file_type = "docx"

    comment_source = working_path if working_path.suffix.lower() == ".docx" else None
    if comment_source is not None:
        comment_anchors = extract_docx_comments_with_anchors(comment_source)
        style_hints = extract_docx_style_hints(comment_source)
        if comment_anchors:
            print(f"[批注] 抽取到 {len(comment_anchors)} 条批注锚点")
        if style_hints:
            print(f"[样式] 抽取到 {len(style_hints)} 条样式提示")

    backend_error = ""
    if actual_markdown_backend == "docling":
        print(f"[Docling] 转换开始，device={device}, file_type={effective_file_type}")
        document, backend_error = run_docling(conversion_input_path, file_type=effective_file_type, device=device)
        if backend_error:
            elapsed_seconds = round(time.time() - start_time, 2)
            write_meta(
                output_dir,
                run_id,
                item,
                device,
                elapsed_seconds,
                doc_conversion_info,
                docx_preprocess_info,
                markdown_backend,
                actual_markdown_backend,
                "error",
                "",
                backend_error,
                comment_anchors,
                style_hints,
                inline_stats,
            )
            print(f"[失败] Docling error: {backend_error[:200]}")
            return {
                "sample_id": item.sample_id,
                "source": str(item.source_path),
                "output_subdir": item.output_subdir.as_posix(),
                "status": "failed",
                "reason": "docling_error",
                "error_detail": backend_error,
            }
        print("[导出] 输出 Markdown ...")
        md_status, md_error = export_markdown_from_docling(document, output_dir, apply_postprocess=not no_postprocess)
    else:
        print(f"[Mammoth] 转换开始，file_type={effective_file_type}")
        md_status, md_error = export_markdown_from_mammoth(working_path, output_dir, apply_postprocess=not no_postprocess)

    if md_status == "ok":
        md_path = output_dir / "output.md"
        markdown = md_path.read_text(encoding="utf-8")
        source_paragraphs = extract_docx_visible_paragraphs(comment_source) if comment_source else []
        repaired_markdown, _ = repair_missing_numbered_paragraphs(markdown, source_paragraphs)
        enriched_markdown, inline_stats = inject_inline_annotations(repaired_markdown, comment_anchors, style_hints)
        md_path.write_text(enriched_markdown, encoding="utf-8")

    elapsed_seconds = round(time.time() - start_time, 2)
    write_meta(
        output_dir,
        run_id,
        item,
        device,
        elapsed_seconds,
        doc_conversion_info,
        docx_preprocess_info,
        markdown_backend,
        actual_markdown_backend,
        md_status,
        md_error,
        backend_error,
        comment_anchors,
        style_hints,
        inline_stats,
    )

    if md_status == "ok":
        print(f"[成功] output.md, elapsed={elapsed_seconds}s")
        return {
            "sample_id": item.sample_id,
            "source": str(item.source_path),
            "output_subdir": item.output_subdir.as_posix(),
            "status": "ok",
            "output_md": str(output_dir / "output.md"),
            "comment_anchor_count": len(comment_anchors),
            "style_hint_count": len(style_hints),
            "inline_injection": inline_stats,
            "markdown_backend": actual_markdown_backend,
            "elapsed_seconds": elapsed_seconds,
        }

    print(f"[失败] Markdown 导出失败: {md_error}")
    return _build_conversion_failure_result(item, md_error)


def run_batch(
    items: list[SourceItem],
    run_id: str,
    output_root: Path,
    device: str,
    no_postprocess: bool,
    history_output_roots: list[Path],
    *,
    markdown_backend: str = "auto",
) -> tuple[list[dict[str, Any]], Path]:
    """Run Markdown conversion in batch and write a run summary."""

    results: list[dict[str, Any]] = []
    for item in items:
        results.append(
            process_one(
                item,
                run_id,
                output_root,
                device,
                no_postprocess,
                history_output_roots,
                markdown_backend=markdown_backend,
            )
        )

    ok_count = sum(1 for result in results if result["status"] == "ok")
    fail_count = len(results) - ok_count

    summary_path = output_root / run_id / "run_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "generated_at": datetime.now().isoformat(),
                "total": len(results),
                "ok": ok_count,
                "failed": fail_count,
                "markdown_backend_requested": markdown_backend,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return results, summary_path
