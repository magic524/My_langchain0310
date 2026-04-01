from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from web_ui.config import ALLOWED_SUFFIXES, WORD2MD_OUTPUT_ROOT, WORD2MD_SCRIPT, make_run_id
from web_ui.models import PipelineResult
from web_ui.services.file_store import save_uploaded_file
from web_ui.services.report_loader import build_artifact_paths


class UploadLike(Protocol):
    """Minimal file uploader protocol used by the service layer."""

    name: str

    def getbuffer(self) -> bytes: ...


def _validate_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_SUFFIXES:
        msg = "仅支持 doc 或 docx 文件。"
        raise ValueError(msg)
    return suffix


def _build_command(input_path: Path, run_id: str) -> list[str]:
    return [
        sys.executable,
        str(WORD2MD_SCRIPT),
        "--input",
        str(input_path),
        "--output",
        run_id,
        "--output-dir",
        str(WORD2MD_OUTPUT_ROOT),
    ]


def _decode_subprocess_output(raw: bytes) -> str:
    """Decode child-process output with Windows-friendly fallbacks."""

    if not raw:
        return ""

    for encoding in ("utf-8", "utf-8-sig", "gb18030", "cp936"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run_word_to_md(uploaded_file: UploadLike) -> PipelineResult:
    """Persist an upload and run the V0 `word2md` pipeline."""

    try:
        _validate_suffix(uploaded_file.name)
    except ValueError as exc:
        return PipelineResult(
            stage="word2md",
            run_id="",
            input_file=uploaded_file.name,
            error_message=str(exc),
        )

    run_id = make_run_id()
    stored = save_uploaded_file(uploaded_file, run_id=run_id)
    command = _build_command(stored.file_path, run_id)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    completed = subprocess.run(
        command,
        capture_output=True,
        text=False,
        cwd=str(WORD2MD_SCRIPT.parents[1]),
        env=env,
        check=False,
    )
    stdout_text = _decode_subprocess_output(completed.stdout)
    stderr_text = _decode_subprocess_output(completed.stderr)

    summary_path = WORD2MD_OUTPUT_ROOT / run_id / "run_summary.json"
    if completed.returncode != 0:
        return PipelineResult(
            stage="word2md",
            run_id=run_id,
            input_file=str(stored.file_path),
            word2md_run_root=str(summary_path.parent),
            error_message=f"word2md 执行失败，退出码: {completed.returncode}",
            command=subprocess.list2cmdline(command),
            stdout=stdout_text,
            stderr=stderr_text,
        )

    if not summary_path.exists():
        return PipelineResult(
            stage="word2md",
            run_id=run_id,
            input_file=str(stored.file_path),
            word2md_run_root=str(summary_path.parent),
            error_message=f"word2md 已执行，但未找到运行摘要: {summary_path}",
            command=subprocess.list2cmdline(command),
            stdout=stdout_text,
            stderr=stderr_text,
        )

    artifact_paths = build_artifact_paths(summary_path)
    return PipelineResult(
        stage="word2md",
        run_id=run_id,
        input_file=str(stored.file_path),
        word2md_run_root=str(summary_path.parent),
        artifact_paths=artifact_paths,
        command=subprocess.list2cmdline(command),
        stdout=stdout_text,
        stderr=stderr_text,
    )
