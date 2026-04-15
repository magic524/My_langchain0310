from __future__ import annotations

import re
from difflib import SequenceMatcher


def compact_text(text: str) -> str:
    """压缩重复空白，保留可读性。"""

    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    """规范化文本，用于模糊匹配和标题比较。"""

    cleaned = str(text)
    cleaned = re.sub(r"[`*_>#\[\]()~|]", "", cleaned)
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    cleaned = cleaned.replace("：", ":").replace("，", ",").replace("；", ";").replace("。", ".")
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.lower().strip()


def short_preview(text: str, *, limit: int = 80) -> str:
    """生成短预览文本，用于日志和回退标题。"""

    compact = compact_text(text)
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def safe_filename(value: str) -> str:
    """将标识符转换为文件系统安全文件名。"""

    cleaned = "".join(char if char not in '<>:"/\\|?*' else "_" for char in str(value)).strip().rstrip(".")
    return cleaned or "output"


def text_similarity(left: str, right: str) -> float:
    """计算文本相似度，用于去重与锚点匹配。"""

    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(a=left_norm, b=right_norm).ratio()
