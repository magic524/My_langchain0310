from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
WEB_UI_ROOT = CURRENT_FILE.parents[2]
PROJECT_ROOT = CURRENT_FILE.parents[4]
WORD2MD_SCRIPT = PROJECT_ROOT / "Contract_Review_System" / "word2md" / "scripts" / "main.py"
WEB_UI_OUTPUT_ROOT = WEB_UI_ROOT / "outputs"
WEB_UI_UPLOAD_ROOT = WEB_UI_OUTPUT_ROOT / "uploads"
WORD2MD_OUTPUT_ROOT = PROJECT_ROOT / "data" / "contract_review_outputs" / "word2md"

PAGE_TITLE = "合同转换 Demo"
PAGE_ICON = "📄"
ALLOWED_SUFFIXES = {"doc", "docx"}


def sanitize_filename(name: str) -> str:
    """Normalize a filename fragment for folder naming."""

    stem = Path(name).stem.strip().lower()
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^a-z0-9\u4e00-\u9fff\-_]+", "-", stem)
    stem = re.sub(r"-+", "-", stem).strip("-")
    return stem or "unnamed"


def make_run_id() -> str:
    """Build a Web UI run identifier."""

    return "webui_" + datetime.now().strftime("%Y%m%d_%H%M%S")
