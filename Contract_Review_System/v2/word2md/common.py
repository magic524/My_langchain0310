"""word2md 公共配置与通用工具。"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "合同数据-2026.3.12"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "outputs_md"
LEGACY_OUTPUT_DIR = REPO_ROOT / "Contract_Review_System" / "datatype_test" / "outputs_md"

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DOCX_NS = {
    **WORD_NS,
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}

for prefix, uri in {
    "w": WORD_NS["w"],
    "mc": DOCX_NS["mc"],
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
}.items():
    ET.register_namespace(prefix, uri)


@dataclass(slots=True)
class SourceItem:
    """单个待转换文件的描述信息。"""

    sample_id: str
    source_path: Path
    file_type: str
    output_subdir: Path


def make_run_id() -> str:
    """生成默认运行批次编号。"""

    return datetime.now().strftime("%Y%m%d_%H%M%S")


def slugify_name(file_path: Path) -> str:
    """将文件名规范化为可复用的输出目录名。"""

    stem = file_path.stem.strip().lower()
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^a-z0-9\u4e00-\u9fff\-_]+", "-", stem)
    stem = re.sub(r"-+", "-", stem).strip("-")
    return stem or "unnamed"


def resolve_path(path_str: str) -> Path:
    """将相对路径解析到仓库根目录，绝对路径原样返回。"""

    candidate = Path(path_str).expanduser()
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve()


def collect_sources(input_file: str | None, input_dir: str | None, recursive: bool) -> list[SourceItem]:
    """收集待转换的 Word 文件。"""

    if bool(input_file) == bool(input_dir):
        raise ValueError("必须二选一：`--input-file` 或 `--input-dir`。")

    if input_file:
        path = resolve_path(input_file)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"输入文件不存在：{path}")
        file_type = path.suffix.lower().lstrip(".")
        if file_type not in {"doc", "docx"}:
            raise ValueError(f"仅支持 `.doc/.docx`，当前文件为：{path}")
        sample_id = slugify_name(path)
        return [
            SourceItem(
                sample_id=sample_id,
                source_path=path.resolve(),
                file_type=file_type,
                output_subdir=Path(sample_id),
            )
        ]

    source_dir = resolve_path(input_dir or "")
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"输入目录不存在：{source_dir}")

    patterns = ["*.doc", "*.docx"] if not recursive else ["**/*.doc", "**/*.docx"]
    file_paths: list[Path] = []
    for pattern in patterns:
        file_paths.extend(source_dir.glob(pattern))

    candidates = sorted({path.resolve() for path in file_paths if path.is_file() and not path.name.startswith("~$")})
    if not candidates:
        raise FileNotFoundError(f"目录中未找到 `.doc/.docx` 文件：{source_dir}")

    items: list[SourceItem] = []
    for path in candidates:
        file_type = path.suffix.lower().lstrip(".")
        relative_no_suffix = path.relative_to(source_dir.resolve()).with_suffix("")
        items.append(
            SourceItem(
                sample_id=relative_no_suffix.as_posix(),
                source_path=path,
                file_type=file_type,
                output_subdir=relative_no_suffix,
            )
        )
    return items


def normalize_whitespace(text: str) -> str:
    """压缩多余空白，方便后续做模糊匹配。"""

    return re.sub(r"\s+", " ", text).strip()


def dedupe_nonempty_texts(values: list[str]) -> list[str]:
    """去重并保留顺序，同时过滤空文本。"""

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_whitespace(value)
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped
