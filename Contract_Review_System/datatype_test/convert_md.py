"""
Markdown-only 合同转换脚本
==========================
用途：将 .doc/.docx 合同统一转换为 Markdown，面向后续模型输入。

能力：
1) 单文件输入：--input-file
2) 文件夹批量输入：--input-dir（可选 --recursive）
3) 仅输出 Markdown 与元数据，不生成 HTML/JSON/对比报告

输出结构（默认）：
  outputs_md/{run_id}/{sample_id}/
    output.md
    meta.json

示例：
  python convert_md.py --input-file "data/.../合同.docx"
  python convert_md.py --input-dir "data/合同数据-2026.3.12" --recursive
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_OUTPUTS_DIR = SCRIPT_DIR / "outputs_md"
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _import_docling():
    """延迟导入 Docling，失败时给出友好提示并退出。"""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter, WordFormatOption

        return DocumentConverter, InputFormat, WordFormatOption
    except ImportError as exc:
        print(
            f"[错误] 无法导入 docling：{exc}\n"
            "请确保已激活 langchain 环境并安装了 docling：\n"
            "  conda activate langchain && pip install docling"
        )
        sys.exit(1)


def make_run_id() -> str:
    """生成基于时间戳的唯一运行 ID。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def slugify_name(file_path: Path) -> str:
    """将文件名规范化为输出目录 ID。"""
    stem = file_path.stem.strip().lower()
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^a-z0-9\u4e00-\u9fff\-_]+", "-", stem)
    stem = re.sub(r"-+", "-", stem).strip("-")
    return stem or "unnamed"


_CHINESE_NUMS = [
    "零",
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
    "十一",
    "十二",
    "十三",
    "十四",
    "十五",
    "十六",
    "十七",
    "十八",
    "十九",
    "二十",
]


def _chinese_num_to_int(token: str) -> int | None:
    if token in _CHINESE_NUMS:
        return _CHINESE_NUMS.index(token)
    return None


def _int_to_chinese_num(value: int) -> str:
    if 1 <= value < len(_CHINESE_NUMS):
        return _CHINESE_NUMS[value]
    return str(value)


def postprocess_legal_markdown(md_text: str) -> str:
    """对合同 Markdown 做轻量纠偏，保留表格与标注可读性。"""
    section_re = re.compile(r"^\s*\*\*([一二三四五六七八九十]+)、([^*]+)\*\*\s*$")
    bullet_bold_re = re.compile(r"^\s*-\s+\*\*([^*]+)\*\*\s*$")
    subsec_re = re.compile(r"^\s*\*\*（[一二三四五六七八九十]+）[^*]*\*\*\s*$")
    num_dot_re = re.compile(r"^\s*(\d+)\.\s+(.*)$")

    lines = md_text.splitlines()
    pass1: list[str] = []
    last_section_num: int | None = None

    for line in lines:
        sec_match = section_re.match(line)
        if sec_match:
            section_num = _chinese_num_to_int(sec_match.group(1))
            if section_num is not None:
                last_section_num = section_num
            pass1.append(line.strip())
            continue

        bullet_match = bullet_bold_re.match(line)
        if bullet_match:
            title = bullet_match.group(1).strip()
            if title.startswith("（"):
                pass1.append(f"**{title}**")
                continue
            if last_section_num is not None:
                next_num = last_section_num + 1
                pass1.append(f"**{_int_to_chinese_num(next_num)}、{title}**")
                last_section_num = next_num
            else:
                pass1.append(f"**{title}**")
            continue

        pass1.append(line)

    pass2: list[str] = []
    in_subsection = False
    subsection_index = 0

    for line in pass1:
        stripped = line.strip()
        if section_re.match(stripped):
            in_subsection = False
            subsection_index = 0
            pass2.append(stripped)
            continue

        if subsec_re.match(stripped):
            in_subsection = True
            subsection_index = 0
            pass2.append(stripped)
            continue

        num_match = num_dot_re.match(line)
        if num_match and in_subsection:
            subsection_index += 1
            content = num_match.group(2).strip()
            pass2.append(f"{subsection_index}. {content}")
            continue

        if line.startswith("    "):
            if section_re.match(stripped) or subsec_re.match(stripped):
                pass2.append(stripped)
                continue
            if num_match:
                pass2.append(f"{num_match.group(1)}. {num_match.group(2).strip()}")
                continue

        pass2.append(line)

    # Pass 3: 结构与换行修复（标题识别、图片占位、异常缩进、段落空行）
    pass3: list[str] = []
    first_major_heading_found = False
    major_heading_re = re.compile(r"^\*\*[一二三四五六七八九十]+、[^*]+\*\*$")
    sub_heading_re = re.compile(r"^\*\*（[一二三四五六七八九十]+）[^*]*\*\*$")

    for idx, raw_line in enumerate(pass2):
        line = raw_line.rstrip()

        # 清理异常缩进（保留列表缩进与表格）
        if line.startswith("    ") and not line.lstrip().startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5.", "|")):
            line = line.lstrip()

        # 规范图片占位写法与缩进
        if "<!-- image -->" in line:
            line = "<!-- image -->"

        stripped = line.strip()
        if not stripped:
            pass3.append("")
            continue

        # 识别文档主标题（仅在正文前段出现一次）
        if not first_major_heading_found and idx <= 20:
            if (
                stripped.startswith("**")
                and stripped.endswith("**")
                and "协议" in stripped
                and len(stripped) <= 60
            ):
                title_text = stripped[2:-2].strip()
                if title_text:
                    line = f"# {title_text}"
                    stripped = line
            elif (
                "协议" in stripped
                and len(stripped) <= 50
                and not stripped.startswith("#")
                and "：" not in stripped
            ):
                line = f"# {stripped}"
                stripped = line
            if stripped.startswith("# ") or major_heading_re.match(stripped):
                first_major_heading_found = True

        if major_heading_re.match(stripped) or sub_heading_re.match(stripped) or stripped.startswith("# "):
            if pass3 and pass3[-1] != "":
                pass3.append("")
            pass3.append(stripped)
            pass3.append("")
            continue

        if stripped == "<!-- image -->":
            if pass3 and pass3[-1] != "":
                pass3.append("")
            pass3.append(stripped)
            pass3.append("")
            continue

        pass3.append(line)

    # 清理多余空行（最多保留 1 个空行）
    compact: list[str] = []
    blank_run = 0
    for line in pass3:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                compact.append("")
            continue
        blank_run = 0
        compact.append(line)

    output = "\n".join(compact)
    if md_text.endswith("\n"):
        output += "\n"
    return output


def _try_libreoffice(doc_path: Path, out_dir: Path) -> Path | None:
    """尝试用 LibreOffice soffice 将 .doc 转为 .docx。"""
    try:
        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(doc_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        expected = out_dir / (doc_path.stem + ".docx")
        if result.returncode == 0 and expected.exists():
            return expected
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _try_win32com(doc_path: Path, out_dir: Path) -> Path | None:
    """尝试用 Word COM 将 .doc 转为 .docx。"""
    target = out_dir / (doc_path.stem + ".docx")

    try:
        import pythoncom  # type: ignore[import]
        import win32com.client  # type: ignore[import]

        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(doc_path.resolve()))
        doc.SaveAs(str(target.resolve()), FileFormat=16)
        doc.Close(False)
        word.Quit()
        pythoncom.CoUninitialize()
        if target.exists():
            return target
    except Exception:
        pass

    try:
        import comtypes.client  # type: ignore[import]

        word = comtypes.client.CreateObject("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(doc_path.resolve()))
        doc.SaveAs(str(target.resolve()), FileFormat=16)
        doc.Close()
        word.Quit()
        if target.exists():
            return target
    except Exception:
        pass

    return None


def convert_doc_to_docx(doc_path: Path, work_dir: Path) -> tuple[Path | None, str]:
    """转换 .doc -> .docx，按优先级 LibreOffice -> Word COM。"""
    work_dir.mkdir(parents=True, exist_ok=True)

    docx_path = _try_libreoffice(doc_path, work_dir)
    if docx_path:
        return docx_path, "libreoffice"

    docx_path = _try_win32com(doc_path, work_dir)
    if docx_path:
        return docx_path, "win32com"

    return None, (
        "all_methods_failed: "
        "LibreOffice (soffice not found or error) "
        "and Word COM (pywin32/comtypes unavailable or Microsoft Word not installed) both unavailable"
    )


def run_docling(input_path: Path, device: str = "cpu") -> tuple[object | None, str]:
    """对 .docx 运行 Docling 转换。"""
    DocumentConverter, InputFormat, WordFormatOption = _import_docling()
    try:
        converter = DocumentConverter(
            format_options={
                InputFormat.DOCX: WordFormatOption(),
            }
        )
        result = converter.convert(str(input_path))
        return result.document, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


def export_markdown(document, out_dir: Path, apply_postprocess: bool) -> tuple[str, str]:
    """导出 Markdown。返回 (status, error_msg)。"""
    try:
        md_text = document.export_to_markdown(
            page_break_placeholder="\n\n---\n\n",
            mark_annotations=True,
        )
        if apply_postprocess:
            md_text = postprocess_legal_markdown(md_text)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "output.md").write_text(md_text, encoding="utf-8")
        return "ok", ""
    except Exception as exc:
        return "error", str(exc)


def resolve_source_path(path_str: str) -> Path:
    """支持绝对路径和相对项目根路径。"""
    candidate = Path(path_str).expanduser()
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


@dataclass(slots=True)
class SourceItem:
    sample_id: str
    source_path: Path
    file_type: str
    output_subdir: Path


def collect_sources(input_file: str | None, input_dir: str | None, recursive: bool) -> list[SourceItem]:
    """根据参数收集待转换源文件。"""
    if bool(input_file) == bool(input_dir):
        raise ValueError("必须二选一：--input-file 或 --input-dir")

    items: list[SourceItem] = []
    if input_file:
        path = resolve_source_path(input_file)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"输入文件不存在：{path}")
        ext = path.suffix.lower().lstrip(".")
        if ext not in {"doc", "docx"}:
            raise ValueError(f"仅支持 .doc/.docx，当前：{path}")
        out_subdir = Path(slugify_name(path))
        items.append(SourceItem(sample_id=slugify_name(path), source_path=path, file_type=ext, output_subdir=out_subdir))
        return items

    dir_path = resolve_source_path(input_dir or "")
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"输入文件夹不存在：{dir_path}")

    patterns = ["*.doc", "*.docx"] if not recursive else ["**/*.doc", "**/*.docx"]
    file_paths: list[Path] = []
    for pattern in patterns:
        file_paths.extend(dir_path.glob(pattern))

    filtered = [p for p in file_paths if p.is_file() and not p.name.startswith("~$")]
    filtered = sorted(set(filtered))
    if not filtered:
        raise FileNotFoundError(f"目录下未找到 .doc/.docx 文件：{dir_path}")

    for path in filtered:
        file_type = path.suffix.lower().lstrip(".")
        rel_no_suffix = path.resolve().relative_to(dir_path.resolve()).with_suffix("")
        sid = rel_no_suffix.as_posix()
        items.append(
            SourceItem(
                sample_id=sid,
                source_path=path.resolve(),
                file_type=file_type,
                output_subdir=rel_no_suffix,
            )
        )
    return items


def _normalize_whitespace(text: str) -> str:
    """压缩空白并保留文本可读性。"""
    return re.sub(r"\s+", " ", text).strip()


def _paragraph_text(paragraph: ET.Element) -> str:
    """抽取段落可见文本。"""
    parts: list[str] = []
    for node in paragraph.findall(".//w:t", WORD_NS):
        if node.text:
            parts.append(node.text)
    return _normalize_whitespace("".join(parts))


def extract_docx_comments_with_anchors(docx_path: Path) -> list[dict]:
    """抽取 docx 批注及其段落锚点，便于模型关联原文位置。"""
    if not docx_path.exists():
        return []

    comments_map: dict[str, dict] = {}
    anchors: list[dict] = []

    try:
        with zipfile.ZipFile(docx_path) as archive:
            if "word/comments.xml" in archive.namelist():
                comments_root = ET.fromstring(archive.read("word/comments.xml"))
                for comment_node in comments_root.findall(".//w:comment", WORD_NS):
                    comment_id = comment_node.attrib.get(
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id",
                        "",
                    )
                    author = comment_node.attrib.get(
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author",
                        "未知作者",
                    )
                    text_parts: list[str] = []
                    for paragraph in comment_node.findall(".//w:p", WORD_NS):
                        paragraph_text = _paragraph_text(paragraph)
                        if paragraph_text:
                            text_parts.append(paragraph_text)
                    comments_map[comment_id] = {
                        "comment_id": comment_id,
                        "author": author,
                        "comment_text": _normalize_whitespace(" ".join(text_parts)),
                    }

            document_root = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = document_root.findall(".//w:p", WORD_NS)

            for idx, paragraph in enumerate(paragraphs, start=1):
                paragraph_text = _paragraph_text(paragraph)
                if not paragraph_text:
                    continue

                started_ids = [
                    node.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id", "")
                    for node in paragraph.findall(".//w:commentRangeStart", WORD_NS)
                ]
                ref_ids = [
                    node.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id", "")
                    for node in paragraph.findall(".//w:commentReference", WORD_NS)
                ]
                ids = [cid for cid in {*(started_ids or []), *(ref_ids or [])} if cid]

                for cid in ids:
                    comment_payload = comments_map.get(
                        cid,
                        {
                            "comment_id": cid,
                            "author": "未知作者",
                            "comment_text": "",
                        },
                    )
                    anchors.append(
                        {
                            "comment_id": comment_payload["comment_id"],
                            "author": comment_payload["author"],
                            "comment_text": comment_payload["comment_text"],
                            "paragraph_index": idx,
                            "paragraph_excerpt": paragraph_text[:180],
                        }
                    )
    except Exception:
        return []

    # 去重，避免同一段多次引用同一 comment id
    dedup: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for item in anchors:
        key = (item["comment_id"], item["paragraph_index"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def extract_docx_style_hints(docx_path: Path) -> list[dict]:
    """抽取 docx 的样式提示（颜色/高亮/下划线/斜体），用于就地注入到 Markdown。"""
    if not docx_path.exists():
        return []

    hints: list[dict] = []
    try:
        with zipfile.ZipFile(docx_path) as archive:
            document_root = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = document_root.findall(".//w:p", WORD_NS)

            for idx, paragraph in enumerate(paragraphs, start=1):
                paragraph_text = _paragraph_text(paragraph)
                if not paragraph_text:
                    continue

                styles: set[str] = set()
                colors: set[str] = set()

                for run in paragraph.findall(".//w:r", WORD_NS):
                    rpr = run.find("w:rPr", WORD_NS)
                    if rpr is None:
                        continue

                    if rpr.find("w:i", WORD_NS) is not None:
                        styles.add("italic")

                    underline = rpr.find("w:u", WORD_NS)
                    if underline is not None:
                        u_val = underline.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
                        if not u_val or u_val.lower() != "none":
                            styles.add("underline")

                    color_node = rpr.find("w:color", WORD_NS)
                    if color_node is not None:
                        color_val = color_node.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
                        if color_val and color_val.lower() not in {"auto", "000000"}:
                            colors.add(f"color#{color_val.upper()}")

                    hl_node = rpr.find("w:highlight", WORD_NS)
                    if hl_node is not None:
                        hl_val = hl_node.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
                        if hl_val and hl_val.lower() != "none":
                            styles.add(f"highlight:{hl_val}")

                # 粗体在 Markdown 中通常已被保留，这里聚焦 Docling Markdown 难表达的样式。
                tags = sorted([*styles, *colors])
                if not tags:
                    continue

                hints.append(
                    {
                        "paragraph_index": idx,
                        "paragraph_excerpt": paragraph_text[:180],
                        "style_tags": tags,
                    }
                )
    except Exception:
        return []

    return hints


def _normalize_for_match(text: str) -> str:
    """用于段落与 Markdown 行近似匹配的归一化。"""
    normalized = text
    normalized = normalized.replace("\\_", "_")
    normalized = re.sub(r"[`*_>#|\-]+", "", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _find_line_index_for_excerpt(lines: list[str], excerpt: str, start_idx: int = 0) -> int | None:
    """在 Markdown 中查找与原段落片段最接近的行索引。"""
    ex = _normalize_for_match(excerpt)
    if len(ex) < 6:
        return None

    # 多档长度匹配，先长后短。
    candidates = [ex[:40], ex[:28], ex[:18], ex[:12]]
    candidates = [c for c in candidates if len(c) >= 8]
    if not candidates:
        return None

    for i in range(start_idx, len(lines)):
        line_norm = _normalize_for_match(lines[i])
        if len(line_norm) < 4:
            continue
        if any(c in line_norm for c in candidates):
            return i

    for i in range(0, start_idx):
        line_norm = _normalize_for_match(lines[i])
        if len(line_norm) < 4:
            continue
        if any(c in line_norm for c in candidates):
            return i

    return None


def inject_inline_annotations(md_text: str, comment_anchors: list[dict], style_hints: list[dict]) -> tuple[str, dict]:
    """将批注和样式提示直接追加到命中原文行尾。"""
    lines = md_text.splitlines()
    if not lines:
        return md_text, {
            "comment_matched": 0,
            "comment_unmatched": len(comment_anchors),
            "style_matched": 0,
            "style_unmatched": len(style_hints),
        }

    line_comment_payloads: dict[int, list[str]] = {}
    line_style_payloads: dict[int, list[str]] = {}
    comment_matched = 0
    style_matched = 0

    cursor = 0
    for item in sorted(comment_anchors, key=lambda x: (x.get("paragraph_index", 0), str(x.get("comment_id", "")))):
        idx = _find_line_index_for_excerpt(lines, str(item.get("paragraph_excerpt", "")), start_idx=cursor)
        if idx is None:
            continue
        comment_id = item.get("comment_id", "")
        author = item.get("author", "未知作者")
        para_idx = item.get("paragraph_index", "?")
        comment_text = (item.get("comment_text", "") or "（批注文本为空）").strip()
        marker = f"批注#{comment_id}/段落{para_idx}/作者{author}: {comment_text}"
        line_comment_payloads.setdefault(idx, []).append(marker)
        comment_matched += 1
        cursor = idx

    cursor = 0
    for item in sorted(style_hints, key=lambda x: int(x.get("paragraph_index", 0))):
        idx = _find_line_index_for_excerpt(lines, str(item.get("paragraph_excerpt", "")), start_idx=cursor)
        if idx is None:
            continue
        tags = item.get("style_tags", [])
        if not tags:
            continue
        para_idx = item.get("paragraph_index", "?")
        marker = f"样式/段落{para_idx}: {', '.join(tags)}"
        line_style_payloads.setdefault(idx, []).append(marker)
        style_matched += 1
        cursor = idx

    if not line_comment_payloads and not line_style_payloads:
        return md_text, {
            "comment_matched": 0,
            "comment_unmatched": len(comment_anchors),
            "style_matched": 0,
            "style_unmatched": len(style_hints),
        }

    new_lines: list[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        updated_line = line

        payloads: list[str] = []
        if idx in line_comment_payloads:
            payloads.extend(line_comment_payloads[idx])
        if idx in line_style_payloads:
            payloads.extend(line_style_payloads[idx])

        if payloads:
            joined = "；".join(payloads)
            # 避免破坏 Markdown 表格结构，表格行用下一行追加。
            if stripped.startswith("|") and stripped.endswith("|"):
                new_lines.append(updated_line)
                new_lines.append(f"【{joined}】")
                continue
            if stripped and not stripped.startswith("<!--"):
                updated_line = f"{updated_line}【{joined}】"

        new_lines.append(updated_line)

    merged = "\n".join(new_lines)
    if md_text.endswith("\n"):
        merged += "\n"

    return merged, {
        "comment_matched": comment_matched,
        "comment_unmatched": max(0, len(comment_anchors) - comment_matched),
        "style_matched": style_matched,
        "style_unmatched": max(0, len(style_hints) - style_matched),
    }


def write_meta(
    out_dir: Path,
    run_id: str,
    item: SourceItem,
    device: str,
    elapsed_seconds: float,
    doc_conversion: dict | None,
    md_status: str,
    md_error: str,
    docling_error: str,
    comment_anchors: list[dict],
    style_hints: list[dict],
    inline_stats: dict,
) -> None:
    """写入每个样本的 meta.json。"""
    meta = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "sample_id": item.sample_id,
        "source_path": str(item.source_path),
        "file_type": item.file_type,
        "device": device,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "doc_conversion": doc_conversion,
        "docling_error": docling_error,
        "md_export": {"status": md_status, "error": md_error},
        "comment_anchor_count": len(comment_anchors),
        "comment_anchors": comment_anchors,
        "style_hint_count": len(style_hints),
        "style_hints": style_hints,
        "inline_injection": inline_stats,
        "output_md": str(out_dir / "output.md") if md_status == "ok" else "",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def process_one(item: SourceItem, run_id: str, output_root: Path, device: str, no_postprocess: bool) -> dict:
    """处理单个文件，返回摘要结果。"""
    out_dir = output_root / run_id / item.output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 68}")
    print(f"样本: {item.sample_id}")
    print(f"源文件: {item.source_path}")
    print(f"{'=' * 68}")

    working_path = item.source_path
    doc_conversion_info: dict | None = None
    comment_anchors: list[dict] = []
    style_hints: list[dict] = []
    inline_stats = {
        "comment_matched": 0,
        "comment_unmatched": 0,
        "style_matched": 0,
        "style_unmatched": 0,
    }
    t0 = time.time()

    if item.file_type == "doc":
        print("[预处理] 检测到 .doc，尝试转换为 .docx ...")
        conv_start = time.time()
        docx_path, method = convert_doc_to_docx(item.source_path, out_dir / "_converted")
        conv_elapsed = round(time.time() - conv_start, 2)
        if docx_path:
            doc_conversion_info = {
                "success": True,
                "method": method,
                "elapsed_seconds": conv_elapsed,
                "output_path": str(docx_path),
            }
            working_path = docx_path
            print(f"[预处理] 成功: {method}, {conv_elapsed}s")
        else:
            msg = "doc 预处理失败，跳过 Docling"
            doc_conversion_info = {"success": False, "error": method}
            elapsed = round(time.time() - t0, 2)
            write_meta(
                out_dir,
                run_id,
                item,
                device,
                elapsed,
                doc_conversion_info,
                "error",
                "",
                msg,
                comment_anchors,
                style_hints,
                inline_stats,
            )
            print(f"[失败] {msg}")
            return {
                "sample_id": item.sample_id,
                "source": str(item.source_path),
                "output_subdir": item.output_subdir.as_posix(),
                "status": "failed",
                "reason": msg,
            }

    comment_source = working_path if working_path.suffix.lower() == ".docx" else None
    if comment_source:
        comment_anchors = extract_docx_comments_with_anchors(comment_source)
        style_hints = extract_docx_style_hints(comment_source)
        if comment_anchors:
            print(f"[批注] 抽取到 {len(comment_anchors)} 条批注锚点")
        if style_hints:
            print(f"[样式] 抽取到 {len(style_hints)} 条样式提示")

    print(f"[Docling] 转换开始，device={device}")
    document, docling_error = run_docling(working_path, device=device)
    if docling_error:
        elapsed = round(time.time() - t0, 2)
        write_meta(
            out_dir,
            run_id,
            item,
            device,
            elapsed,
            doc_conversion_info,
            "error",
            "",
            docling_error,
            comment_anchors,
            style_hints,
            inline_stats,
        )
        print(f"[失败] Docling error: {docling_error[:200]}")
        return {
            "sample_id": item.sample_id,
            "source": str(item.source_path),
            "output_subdir": item.output_subdir.as_posix(),
            "status": "failed",
            "reason": "docling_error",
        }

    print("[导出] 输出 Markdown ...")
    md_status, md_error = export_markdown(document, out_dir, apply_postprocess=not no_postprocess)
    if md_status == "ok" and (comment_anchors or style_hints):
        md_path = out_dir / "output.md"
        current_md = md_path.read_text(encoding="utf-8")
        enriched_md, inline_stats = inject_inline_annotations(current_md, comment_anchors, style_hints)
        md_path.write_text(enriched_md, encoding="utf-8")
    elapsed = round(time.time() - t0, 2)
    write_meta(
        out_dir,
        run_id,
        item,
        device,
        elapsed,
        doc_conversion_info,
        md_status,
        md_error,
        "",
        comment_anchors,
        style_hints,
        inline_stats,
    )

    if md_status == "ok":
        print(f"[成功] output.md, elapsed={elapsed}s")
        return {
            "sample_id": item.sample_id,
            "source": str(item.source_path),
            "output_subdir": item.output_subdir.as_posix(),
            "status": "ok",
            "output_md": str(out_dir / "output.md"),
            "comment_anchor_count": len(comment_anchors),
            "style_hint_count": len(style_hints),
            "inline_injection": inline_stats,
            "elapsed_seconds": elapsed,
        }

    print(f"[失败] markdown 导出失败: {md_error}")
    return {
        "sample_id": item.sample_id,
        "source": str(item.source_path),
        "output_subdir": item.output_subdir.as_posix(),
        "status": "failed",
        "reason": md_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Markdown-only 合同转换：支持单文件与批量文件夹输入，仅输出 md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python convert_md.py --input-file data/.../合同.docx\n"
            "  python convert_md.py --input-dir data/合同数据-2026.3.12 --recursive\n"
            "  python convert_md.py --input-dir data/... --output-dir Contract_Review_System/datatype_test/outputs_md\n"
        ),
    )
    parser.add_argument("--input-file", default=None, help="输入单个 .doc/.docx 文件路径")
    parser.add_argument("--input-dir", default=None, help="输入目录路径，自动转换目录内 doc/docx")
    parser.add_argument("--recursive", action="store_true", help="目录模式下递归扫描子目录")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUTS_DIR),
        help="输出根目录，默认 datatype_test/outputs_md",
    )
    parser.add_argument("--run-id", default=None, help="自定义 run id，不传则自动时间戳")
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["auto", "cpu", "cuda", "mps"],
        help="推理设备标记（记录用）",
    )
    parser.add_argument(
        "--no-postprocess",
        action="store_true",
        help="关闭 Markdown 后处理（默认开启，建议保留）",
    )
    args = parser.parse_args()

    run_id = args.run_id or make_run_id()
    output_root = resolve_source_path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    items = collect_sources(args.input_file, args.input_dir, args.recursive)

    print(f"\n{'#' * 68}")
    print("Markdown-only Contract Converter")
    print(f"Run ID      : {run_id}")
    print(f"Items       : {len(items)}")
    print(f"Output Root : {output_root}")
    print(f"Device      : {args.device}")
    print(f"Postprocess : {not args.no_postprocess}")
    print(f"{'#' * 68}\n")

    results: list[dict] = []
    for item in items:
        result = process_one(item, run_id, output_root, args.device, args.no_postprocess)
        results.append(result)

    ok_count = sum(1 for x in results if x["status"] == "ok")
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
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{'=' * 68}")
    print("All done")
    print(f"Success : {ok_count}")
    print(f"Failed  : {fail_count}")
    print(f"Summary : {summary_path}")
    print(f"{'=' * 68}\n")


if __name__ == "__main__":
    main()
