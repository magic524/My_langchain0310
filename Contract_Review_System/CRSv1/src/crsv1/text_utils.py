from __future__ import annotations

import re
from difflib import SequenceMatcher


def compact_text(text: str) -> str:
    """Collapse repeated whitespace while preserving readability."""

    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy matching and title comparison."""

    cleaned = str(text)
    cleaned = re.sub(r"[`*_>#\[\]()~|]", "", cleaned)
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    cleaned = cleaned.replace("：", ":").replace("，", ",").replace("；", ";").replace("。", ".")
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.lower().strip()


def short_preview(text: str, *, limit: int = 80) -> str:
    """Build a short preview for logs and fallback headings."""

    compact = compact_text(text)
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def safe_filename(value: str) -> str:
    """Convert an identifier to a filesystem-safe filename."""

    cleaned = "".join(char if char not in '<>:"/\\|?*' else "_" for char in str(value)).strip().rstrip(".")
    return cleaned or "output"


def text_similarity(left: str, right: str) -> float:
    """Compute a simple similarity score for deduplication and matching."""

    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(a=left_norm, b=right_norm).ratio()
