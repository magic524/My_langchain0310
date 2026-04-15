"""GUI service layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from Contract_Review_System.common.local_llm_client import load_runtime_config, resolve_runtime_env_path
from Contract_Review_System.pipeline.src.contract_review_pipeline.pipeline_crsv1 import (
    run_contract_review_pipeline,
)


ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]

CURRENT_FILE = Path(__file__).resolve()
CONTRACT_REVIEW_ROOT = CURRENT_FILE.parents[1]
DEFAULT_OUTPUT_ROOT = CONTRACT_REVIEW_ROOT / "outputs"
DEFAULT_WORD2MD_OUTPUT_ROOT = CONTRACT_REVIEW_ROOT / "data" / "contract_review_outputs" / "word2md"


@dataclass(slots=True)
class GuiReviewRequest:
    """A single review request from the GUI."""

    input_path: str
    review_stance: str
    extra_user_instruction: str = ""
    display_risk_levels: list[str] | None = None


@dataclass(slots=True)
class GuiReviewResult:
    """A minimal result payload for GUI display."""

    pipeline_output_dir: str
    primary_comment_file: str
    primary_report_path: str
    comment_output_dir: str
    summary_path: str
    log_path: str


class GuiPipelineService:
    """Adapter layer between GUI input and the production pipeline."""

    def __init__(
        self,
        *,
        output_root: Path = DEFAULT_OUTPUT_ROOT,
        word2md_output_root: Path = DEFAULT_WORD2MD_OUTPUT_ROOT,
    ) -> None:
        self.output_root = output_root.resolve()
        self.word2md_output_root = word2md_output_root.resolve()

    def run(
        self,
        request: GuiReviewRequest,
        *,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> GuiReviewResult:
        """Execute one GUI-triggered review task."""

        input_path = Path(request.input_path).expanduser().resolve()
        if not input_path.exists():
            msg = f"输入文件不存在：{input_path}"
            raise FileNotFoundError(msg)
        if input_path.suffix.lower() not in {".doc", ".docx", ".pdf"}:
            msg = f"当前 GUI 仅支持 doc/docx/pdf：{input_path.name}"
            raise ValueError(msg)

        run_name = self._default_run_name(input_path)
        pipeline_output_dir = self._make_unique_dir(self.output_root / run_name)

        runtime = load_runtime_config(resolve_runtime_env_path())

        result = run_contract_review_pipeline(
            input_value=str(input_path),
            run_name=pipeline_output_dir.name,
            runtime=runtime,
            pipeline_output_dir=pipeline_output_dir,
            word2md_output_root=self.word2md_output_root,
            review_stance=request.review_stance,
            extra_user_instruction=request.extra_user_instruction,
            display_risk_levels=request.display_risk_levels,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
        return GuiReviewResult(
            pipeline_output_dir=result["pipeline_output_dir"],
            primary_comment_file=result.get("primary_comment_file", ""),
            primary_report_path=result.get("primary_report_path", ""),
            comment_output_dir=result["comment_output_dir"],
            summary_path=result["summary_path"],
            log_path=result["log_path"],
        )

    @staticmethod
    def _default_run_name(input_path: Path) -> str:
        """Build a filesystem-safe run directory name from the input file."""

        cleaned = "".join(char if char not in '<>:"/\\|?*' else "_" for char in input_path.stem).strip()
        return cleaned.rstrip(".") or "contract_review_run"

    @staticmethod
    def _make_unique_dir(base_dir: Path) -> Path:
        """Return a unique directory path by appending a numeric suffix if needed."""

        if not base_dir.exists():
            return base_dir

        index = 2
        while True:
            candidate = base_dir.parent / f"{base_dir.name}_{index}"
            if not candidate.exists():
                return candidate
            index += 1
