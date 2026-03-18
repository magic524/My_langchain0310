from __future__ import annotations

import re
from difflib import SequenceMatcher


def compact_text(text: str) -> str:
    """压缩空白，保留可读性。"""

    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    """用于匹配的归一化文本。"""

    cleaned = re.sub(r"[`*_>#\[\]()~|]", "", text)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.strip().lower()


def short_preview(text: str, *, limit: int = 80) -> str:
    """生成上下文摘要。"""

    compact = compact_text(text)
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    """判断文本是否包含任一关键词。"""

    return any(marker in text for marker in markers)


def extract_zh_tokens(text: str, *, min_len: int = 2, max_items: int = 16) -> list[str]:
    """提取粗粒度中文 token。"""

    tokens = re.findall(r"[\u4e00-\u9fff]{%d,10}" % min_len, text)
    stop_words = {
        "条款",
        "建议",
        "修改",
        "说明",
        "风险",
        "意见",
        "合同",
        "采纳",
        "部分采纳",
        "未采纳",
        "作者",
    }
    results: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in stop_words or token in seen:
            continue
        seen.add(token)
        results.append(token)
        if len(results) >= max_items:
            break
    return results


def token_overlap_ratio(left: str, right: str) -> float:
    """计算关键词重叠比例。"""

    left_tokens = set(extract_zh_tokens(left))
    right_tokens = set(extract_zh_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def text_similarity(left: str, right: str) -> float:
    """综合字面相似度和关键词重叠。"""

    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    seq_score = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    overlap = token_overlap_ratio(left, right)
    return max(seq_score, overlap)
