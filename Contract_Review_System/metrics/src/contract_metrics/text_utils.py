from __future__ import annotations

import re
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    """Normalize text for matching.

    Args:
        text: Raw text.

    Returns:
        Normalized text without extra spaces and markdown symbols.
    """
    cleaned = re.sub(r"[`*_>#\[\]()~]", "", text)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.strip().lower()


def compact_text(text: str) -> str:
    """Compact whitespace while preserving readable Chinese/English text.

    Args:
        text: Raw text.

    Returns:
        Compacted text with single spaces.
    """
    return re.sub(r"\s+", " ", text).strip()


def extract_zh_keywords(text: str, *, min_len: int = 2, max_items: int = 12) -> list[str]:
    """Extract coarse Chinese keywords for rule matching.

    Args:
        text: Input text.
        min_len: Minimum token length.
        max_items: Maximum number of returned tokens.

    Returns:
        Deduplicated keyword list.
    """
    tokens = re.findall(r"[\u4e00-\u9fff]{%d,8}" % min_len, text)
    stop_words = {
        "条款",
        "建议",
        "修改",
        "说明",
        "风险",
        "意见",
        "合同",
        "部分",
        "采纳",
        "未采纳",
        "原因",
        "作者",
    }
    results: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in stop_words:
            continue
        if token in seen:
            continue
        seen.add(token)
        results.append(token)
        if len(results) >= max_items:
            break
    return results


def token_overlap_ratio(left: str, right: str) -> float:
    """Compute overlap ratio between extracted keyword sets.

    Args:
        left: Left text.
        right: Right text.

    Returns:
        Overlap ratio in [0, 1].
    """
    left_tokens = set(extract_zh_keywords(left))
    right_tokens = set(extract_zh_keywords(right))
    if not left_tokens or not right_tokens:
        return 0.0
    hit = len(left_tokens & right_tokens)
    base = max(len(left_tokens), len(right_tokens))
    return hit / base


def text_similarity(left: str, right: str) -> float:
    """Compute rule-based similarity score.

    Args:
        left: Left text.
        right: Right text.

    Returns:
        Similarity score in [0, 1].
    """
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0

    seq_score = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    overlap = token_overlap_ratio(left, right)
    return max(seq_score, overlap)


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    """Whether text contains any marker.

    Args:
        text: Input text.
        markers: Marker tuple.

    Returns:
        True if any marker exists.
    """
    return any(marker in text for marker in markers)
