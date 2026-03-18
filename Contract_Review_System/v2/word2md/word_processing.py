"""Word 文件预处理：`.doc -> .docx` 转换与 Docling 输入修复。"""

from __future__ import annotations

import copy
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from common import DOCX_NS


def try_libreoffice(doc_path: Path, output_dir: Path) -> Path | None:
    """尝试使用 LibreOffice 将 `.doc` 转为 `.docx`。"""

    try:
        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "docx", "--outdir", str(output_dir), str(doc_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    expected_path = output_dir / f"{doc_path.stem}.docx"
    if result.returncode == 0 and expected_path.exists():
        return expected_path
    return None


def try_win32com(doc_path: Path, output_dir: Path) -> Path | None:
    """尝试使用 Word COM 将 `.doc` 转为 `.docx`。"""

    target_path = output_dir / f"{doc_path.stem}.docx"

    try:
        import pythoncom  # type: ignore[import]
        import win32com.client  # type: ignore[import]

        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        document = word.Documents.Open(str(doc_path.resolve()))
        document.SaveAs(str(target_path.resolve()), FileFormat=16)
        document.Close(False)
        word.Quit()
        pythoncom.CoUninitialize()
        if target_path.exists():
            return target_path
    except Exception:
        pass

    try:
        import comtypes.client  # type: ignore[import]

        word = comtypes.client.CreateObject("Word.Application")
        word.Visible = False
        document = word.Documents.Open(str(doc_path.resolve()))
        document.SaveAs(str(target_path.resolve()), FileFormat=16)
        document.Close()
        word.Quit()
        if target_path.exists():
            return target_path
    except Exception:
        pass

    return None


def detect_word_file_format(path: Path) -> str:
    """探测文件真实容器类型，而不是只看扩展名。"""

    try:
        header = path.read_bytes()[:8]
    except OSError:
        return "unknown"

    if header.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" in names and "word/document.xml" in names:
                    return "docx_package"
        except zipfile.BadZipFile:
            return "unknown"

    if header.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return "ole_doc"
    return "unknown"


def reuse_mislabeled_docx_package(doc_path: Path, work_dir: Path) -> Path | None:
    """复用“扩展名是 `.doc`、实际内容是 docx 包”的文件。"""

    if detect_word_file_format(doc_path) != "docx_package":
        return None

    work_dir.mkdir(parents=True, exist_ok=True)
    target_path = work_dir / f"{doc_path.stem}.docx"
    shutil.copy2(doc_path, target_path)
    return target_path


def reuse_previous_converted_docx(
    doc_path: Path,
    work_dir: Path,
    cache_roots: list[Path],
    output_subdir: Path,
    *,
    current_run_id: str | None = None,
) -> tuple[Path | None, str]:
    """从历史跑批里复用已成功转换的 `_converted/*.docx`。"""

    candidate_paths: list[Path] = []
    for output_root in cache_roots:
        if not output_root.exists():
            continue
        for run_dir in sorted(output_root.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            if output_root == cache_roots[0] and current_run_id and run_dir.name == current_run_id:
                continue
            candidate_path = run_dir / output_subdir / "_converted" / f"{doc_path.stem}.docx"
            if candidate_path.exists() and detect_word_file_format(candidate_path) == "docx_package":
                candidate_paths.append(candidate_path)

    if not candidate_paths:
        return None, ""

    work_dir.mkdir(parents=True, exist_ok=True)
    source_path = candidate_paths[0]
    target_path = work_dir / f"{doc_path.stem}.docx"
    shutil.copy2(source_path, target_path)
    cache_root = next(root for root in cache_roots if source_path.is_relative_to(root))
    run_name = source_path.relative_to(cache_root).parts[0]
    return target_path, f"previous_run_cache:{run_name}"


def convert_doc_to_docx(
    doc_path: Path,
    work_dir: Path,
    *,
    cache_roots: list[Path] | None = None,
    output_subdir: Path | None = None,
    current_run_id: str | None = None,
) -> tuple[Path | None, str]:
    """将 `.doc` 转为 `.docx`，并保留全部兜底策略。"""

    work_dir.mkdir(parents=True, exist_ok=True)

    disguised_docx_path = reuse_mislabeled_docx_package(doc_path, work_dir)
    if disguised_docx_path:
        return disguised_docx_path, "renamed_docx_package"

    libreoffice_path = try_libreoffice(doc_path, work_dir)
    if libreoffice_path:
        return libreoffice_path, "libreoffice"

    win32com_path = try_win32com(doc_path, work_dir)
    if win32com_path:
        return win32com_path, "win32com"

    if cache_roots and output_subdir is not None:
        cached_docx_path, cache_method = reuse_previous_converted_docx(
            doc_path,
            work_dir,
            cache_roots,
            output_subdir,
            current_run_id=current_run_id,
        )
        if cached_docx_path:
            return cached_docx_path, cache_method

    return None, (
        "all_methods_failed: "
        "LibreOffice (soffice not found or error) "
        "and Word COM (pywin32/comtypes unavailable or Microsoft Word not installed) both unavailable; "
        "no previous converted docx cache found"
    )


def flatten_alternate_content(root: ET.Element) -> int:
    """移除 `mc:AlternateContent` 包裹层，只保留可用分支。"""

    mc_ns = DOCX_NS["mc"]
    parent_map = {child: parent for parent in root.iter() for child in parent}
    replaced_count = 0

    for node in list(root.findall(f".//{{{mc_ns}}}AlternateContent")):
        parent = parent_map.get(node)
        if parent is None:
            continue

        replacement_children: list[ET.Element] = []
        for branch_name in ("Fallback", "Choice"):
            branch = node.find(f"{{{mc_ns}}}{branch_name}")
            if branch is not None and list(branch):
                replacement_children = [copy.deepcopy(child) for child in list(branch)]
                break

        insert_at = list(parent).index(node)
        parent.remove(node)
        for offset, child in enumerate(replacement_children):
            parent.insert(insert_at + offset, child)
        replaced_count += 1

    return replaced_count


def prepare_docx_for_docling(docx_path: Path, work_dir: Path) -> tuple[Path, dict | None]:
    """修复已知会让 Docling 崩溃的 DOCX 标记。"""

    if not docx_path.exists():
        return docx_path, None

    try:
        with zipfile.ZipFile(docx_path) as archive:
            if "word/document.xml" not in archive.namelist():
                return docx_path, None

            document_root = ET.fromstring(archive.read("word/document.xml"))
            alternate_content_count = len(document_root.findall(".//mc:AlternateContent", DOCX_NS))
            if alternate_content_count == 0:
                return docx_path, None

            replaced_count = flatten_alternate_content(document_root)
            if replaced_count == 0:
                return docx_path, None

            work_dir.mkdir(parents=True, exist_ok=True)
            sanitized_path = work_dir / f"{docx_path.stem}.docling.docx"
            sanitized_document_xml = ET.tostring(document_root, encoding="utf-8", xml_declaration=True)

            with zipfile.ZipFile(sanitized_path, "w") as sanitized_zip:
                for info in archive.infolist():
                    payload = (
                        sanitized_document_xml if info.filename == "word/document.xml" else archive.read(info.filename)
                    )
                    sanitized_zip.writestr(info, payload)

        return sanitized_path, {
            "applied": True,
            "reason": "flatten_alternate_content",
            "alternate_content_count": alternate_content_count,
            "output_path": str(sanitized_path),
        }
    except Exception as exc:
        return docx_path, {
            "applied": False,
            "reason": "flatten_alternate_content_failed",
            "error": str(exc),
        }
