from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PipelineResult:
    """Normalized result returned by the V0 review pipeline."""

    stage: str
    run_id: str
    input_file: str
    word2md_run_root: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    error_message: str = ""
    command: str = ""
    stdout: str = ""
    stderr: str = ""
