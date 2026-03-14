"""
Docling 合同格式保真度测试脚本
================================
用途：对 samples.json 中列出的合同原文（.doc/.docx），通过 Docling 统一转换为
      Markdown、HTML、JSON 三种格式，并生成可供人工对比的汇总报告。

输出目录结构：
  outputs/{run_id}/{sample_id}/
    output.md         <- Markdown 导出
    output.html       <- HTML 导出
    output.json       <- 结构化 JSON 导出
    meta.json         <- 本次转换元数据
  reports/{run_id}_summary.md   <- 汇总对比报告

运行示例（conda activate langchain 后在 datatype_test 目录内）：
  python convert.py                              # 转换全部样本，导出全部格式
  python convert.py --sample-id 1-brand-venue   # 只转特定样本
  python convert.py --formats md html           # 只导出 Markdown + HTML
  python convert.py --device cpu                # 指定 CPU 推理（默认 cpu）
  python convert.py --help                      # 查看所有参数

.doc 处理策略（用户决策：先转 docx 再进 Docling）：
  1. LibreOffice soffice（推荐，跨平台）
  2. Win32com Word COM（Windows + Office）
  3. 均失败 -> 写入 meta.json error 字段，在报告中标注警告
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ─── 路径约定 ─────────────────────────────────────────────────────────────────
# 本脚本位于 Contract_Review_System/datatype_test/
# 项目根目录（My_langchain0310/）在两级父目录
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent   # My_langchain0310/
SAMPLES_FILE = SCRIPT_DIR / "samples.json"
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
REPORTS_DIR = SCRIPT_DIR / "reports"


# ─── Docling 导入（延迟，给出友好错误）─────────────────────────────────────────
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


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def load_samples(sample_id: str | None = None) -> list[dict]:
    """从 samples.json 加载样本清单，可选过滤特定 sample_id。"""
    with open(SAMPLES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    samples = data["samples"]
    if sample_id:
        found = [s for s in samples if s["id"] == sample_id]
        if not found:
            available = [s["id"] for s in samples]
            raise ValueError(f"样本 ID '{sample_id}' 不存在。可用：{available}")
        return found
    return samples


def make_run_id() -> str:
    """生成基于时间戳的唯一运行 ID，格式 YYYYMMDD_HHMMSS。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


_CHINESE_NUMS = [
    "零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
]


def _chinese_num_to_int(token: str) -> int | None:
    """将中文数字（支持一到二十）转换为整数。"""
    if token in _CHINESE_NUMS:
        return _CHINESE_NUMS.index(token)
    return None


def _int_to_chinese_num(value: int) -> str:
    """将整数（1-20）转为中文数字。"""
    if 1 <= value < len(_CHINESE_NUMS):
        return _CHINESE_NUMS[value]
    return str(value)


def postprocess_legal_markdown(md_text: str) -> str:
    """
    对 Docling 导出的合同 Markdown 做轻量纠偏：
    1. 补全缺失的章编号（例如 "- **违约责任**" -> "**四、违约责任**"）。
    2. 纠正误判的嵌套列表（将连续缩进的 1. 条款拉平并顺序编号）。
    3. 清理异常缩进的章节标题与小节标题。
    """
    section_re = re.compile(r"^\s*\*\*([一二三四五六七八九十]+)、([^*]+)\*\*\s*$")
    bullet_bold_re = re.compile(r"^\s*-\s+\*\*([^*]+)\*\*\s*$")
    subsec_re = re.compile(r"^\s*\*\*（[一二三四五六七八九十]+）[^*]*\*\*\s*$")
    num_dot_re = re.compile(r"^\s*(\d+)\.\s+(.*)$")

    lines = md_text.splitlines()

    # Pass 1: 补全缺失章编号，并把 "- **标题**" 归一为 "**标题**"
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
            # 小节标题（如（一））不补章号，只去掉 bullet
            if title.startswith("（"):
                pass1.append(f"**{title}**")
                continue

            # 普通粗体标题尝试补全下一章号
            if last_section_num is not None:
                next_num = last_section_num + 1
                numbered = f"**{_int_to_chinese_num(next_num)}、{title}**"
                pass1.append(numbered)
                last_section_num = next_num
            else:
                pass1.append(f"**{title}**")
            continue

        pass1.append(line)

    # Pass 2: 修复异常缩进与误嵌套 1. 列表
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

        # 对明显异常缩进的章/节标题和编号条款做拉平
        if line.startswith("    "):
            if section_re.match(stripped) or subsec_re.match(stripped):
                pass2.append(stripped)
                continue
            if num_match:
                pass2.append(f"{num_match.group(1)}. {num_match.group(2).strip()}")
                continue

        pass2.append(line)

    output = "\n".join(pass2)
    if md_text.endswith("\n"):
        output += "\n"
    return output


# ─── .doc 转 .docx（优先 LibreOffice，其次 Win32com）────────────────────────

def _try_libreoffice(doc_path: Path, out_dir: Path) -> Path | None:
    """尝试用 LibreOffice soffice 将 .doc 转为 .docx。成功返回 .docx 路径，否则 None。"""
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
    """尝试用 Win32com（Word COM）将 .doc 转为 .docx。成功返回 .docx 路径，否则 None。"""
    target = out_dir / (doc_path.stem + ".docx")

    # 路径1：pywin32（当前环境已验证可导入 win32com.client）
    try:
        import pythoncom  # type: ignore[import]
        import win32com.client  # type: ignore[import]

        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(doc_path.resolve()))
        # 16 = wdFormatXMLDocument (.docx)
        doc.SaveAs(str(target.resolve()), FileFormat=16)
        doc.Close(False)
        word.Quit()
        pythoncom.CoUninitialize()
        if target.exists():
            return target
    except Exception:
        pass

    # 路径2：comtypes（作为兼容回退）
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
    """
    转换 .doc -> .docx，按优先级：LibreOffice -> Win32com。

    Returns:
        (docx_path, method_used): 成功时 docx_path 非 None；
        失败时 docx_path 为 None，method_used 描述失败原因。
    """
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


# ─── Docling 转换核心 ─────────────────────────────────────────────────────────

def run_docling(
    input_path: Path,
    device: str = "cpu",
) -> tuple[object | None, str]:
    """
    对 .docx 文件运行 Docling 转换，返回 (result.document, error_msg)。
    成功时 error_msg 为空字符串。

    注意：Word 格式使用 SimplePipeline，不需要加速器配置，device 参数仅供元数据记录。
    """
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


# ─── 格式导出 ─────────────────────────────────────────────────────────────────

def export_formats(document, out_dir: Path, formats: list[str]) -> dict[str, str]:
    """
    将 Docling document 导出为指定格式，写入 out_dir。

    Returns:
        {format: "ok" | "error: <msg>"}
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    if "md" in formats:
        try:
            md_text = document.export_to_markdown(
                page_break_placeholder="\n\n---\n\n",
                mark_annotations=True,
            )
            md_text = postprocess_legal_markdown(md_text)
            (out_dir / "output.md").write_text(md_text, encoding="utf-8")
            results["md"] = "ok"
        except Exception as exc:
            results["md"] = f"error: {exc}"

    if "html" in formats:
        try:
            html_text = document.export_to_html()
            (out_dir / "output.html").write_text(html_text, encoding="utf-8")
            results["html"] = "ok"
        except Exception as exc:
            results["html"] = f"error: {exc}"

    if "json" in formats:
        try:
            doc_dict = document.export_to_dict()
            (out_dir / "output.json").write_text(
                json.dumps(doc_dict, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results["json"] = "ok"
        except Exception as exc:
            results["json"] = f"error: {exc}"

    return results


# ─── 元数据记录 ───────────────────────────────────────────────────────────────

def write_meta(
    out_dir: Path,
    sample: dict,
    run_id: str,
    device: str,
    elapsed_seconds: float,
    doc_conversion: dict | None,
    export_results: dict[str, str],
    docling_error: str,
) -> None:
    """将本次转换的完整元数据写入 meta.json。"""
    meta = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "sample_id": sample["id"],
        "sample_display_name": sample["display_name"],
        "source_path": sample["source_path"],
        "file_type": sample["file_type"],
        "device": device,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "doc_conversion": doc_conversion,
        "docling_error": docling_error,
        "export_results": export_results,
        "outputs": {
            fmt: str(out_dir / f"output.{fmt}")
            for fmt, status in export_results.items()
            if status == "ok"
        },
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─── 汇总报告生成（Markdown）─────────────────────────────────────────────────

def _status_icon(export_results: dict, key: str) -> str:
    v = export_results.get(key, "-")
    return "OK" if v == "ok" else ("FAIL" if isinstance(v, str) and v.startswith("error") else "-")


def build_summary_report(run_id: str, all_metas: list[dict]) -> str:
    """生成汇总对比报告 Markdown，供人工逐维度对比。"""
    lines: list[str] = [
        "# 格式保真度测试汇总报告",
        "",
        f"**Run ID**: `{run_id}`  ",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**样本数量**: {len(all_metas)} 份  ",
        "",
        "---",
        "",
    ]

    # 转换状态总览
    lines += [
        "## 一、转换状态总览",
        "",
        "| 样本 | 文件类型 | doc转换方式 | Markdown | HTML | JSON | 耗时(s) |",
        "|------|---------|------------|---------|------|------|---------|",
    ]
    for m in all_metas:
        doc_info = "原生 docx" if m["file_type"] == "docx" else ""
        dc = m.get("doc_conversion")
        if dc:
            doc_info = f"OK ({dc.get('method', '?')})" if dc.get("success") else "FAIL"

        if m.get("docling_error"):
            row = (
                f"| {m['sample_display_name']} | `.{m['file_type']}` | {doc_info}"
                f" | Docling失败 | Docling失败 | Docling失败 | {m['elapsed_seconds']} |"
            )
        else:
            er = m.get("export_results", {})
            row = (
                f"| {m['sample_display_name']} | `.{m['file_type']}` | {doc_info}"
                f" | {_status_icon(er, 'md')}"
                f" | {_status_icon(er, 'html')}"
                f" | {_status_icon(er, 'json')}"
                f" | {m['elapsed_seconds']} |"
            )
        lines.append(row)

    lines += ["", "---", ""]

    # 逐样本对比材料（供人工填写）
    lines += [
        "## 二、逐样本输出预览与对比（人工填写）",
        "",
        "> 阅读说明：对照原始 Word 文件，在下方空白区域填写你的观察结论。",
        "> 输出文件位置：`outputs/{run_id}/{sample_id}/output.{格式}`",
        "",
    ]

    for m in all_metas:
        sid = m["sample_id"]
        lines += [
            f"### {m['sample_display_name']}（`{sid}`）",
            "",
            f"**源文件**: `{m['source_path']}`  ",
            f"**耗时**: {m['elapsed_seconds']} 秒  ",
            "",
            "#### 表格结构保留",
            "",
            "- [ ] 原文是否含表格：（是 / 否 / 未确认）",
            "- [ ] Markdown 中表格可辨识行列：（是 / 否 / 部分）",
            "- [ ] HTML 中表格结构完整：（是 / 否 / 部分）",
            "- [ ] 表格内容是否有截断或乱序：（无 / 有，说明：）",
            "",
            "#### 标题与层级保留",
            "",
            "- [ ] 章节标题是否转化为 Heading：（是 / 否 / 部分）",
            "- [ ] 编号层级（一、1. 1.1 等）是否维持：（是 / 否）",
            "- [ ] 条款缩进层级是否正确：（是 / 否）",
            "",
            "#### 修订/批注保留",
            "",
            "- [ ] 原文是否含修订/批注：（是 / 否 / 未确认）",
            "- [ ] Markdown 中是否出现批注标记：（是 / 否）",
            "- [ ] HTML 中是否出现批注内容：（是 / 否）",
            "",
            "#### 纯文本完整度",
            "",
            "- [ ] 是否存在乱码：（无 / 有，位置：）",
            "- [ ] 是否有明显截断（合同条款中断）：（无 / 有，位置：）",
            "- [ ] 是否有内容重复：（无 / 有）",
            "- [ ] 总体文本可读性：（优 / 良 / 差）",
            "",
        ]
        if m.get("docling_error"):
            short_err = m["docling_error"][:800]
            lines += [
                "> **[警告] Docling 转换失败，无法生成上述输出文件**  ",
                "> 错误信息：",
                "```",
                short_err,
                "```",
                "",
            ]
        dc = m.get("doc_conversion")
        if dc and not dc.get("success"):
            lines += [
                "> **[警告] .doc 预转换失败**  ",
                f"> 原因：{dc.get('error', '未知')}",
                "> 建议：安装 LibreOffice（soffice 命令）或安装 pywin32 并确认 Word 已安装",
                "",
            ]
        lines.append("---")
        lines.append("")

    # 首轮结论（人工填写）
    lines += [
        "## 三、首轮结论（人工填写）",
        "",
        "### 推荐 v2 输入格式",
        "",
        "| 候选格式 | 表格保真 | 层级保真 | 批注保留 | 程序可解析 | 综合建议 |",
        "|---------|---------|---------|---------|----------|---------|",
        "| Markdown | （填写）| （填写）| （填写）| 是 | （填写）|",
        "| HTML     | （填写）| （填写）| （填写）| 是 | （填写）|",
        "| JSON     | （填写）| （填写）| （填写）| 是 | （填写）|",
        "",
        "**主格式推荐**：（填写）  ",
        "**备选格式/使用场景**：（填写）  ",
        "**待补充方案**：（若 Docling 批注保留不足，v2 阶段补充 python-docx 融合方案）  ",
        "",
        "### 已发现的限制",
        "",
        "- （填写）",
        "",
        "### v2 下一步建议",
        "",
        "- （填写）",
    ]

    return "\n".join(lines)


# ─── 单样本处理流程 ───────────────────────────────────────────────────────────

def _make_failed_meta(
    sample: dict,
    run_id: str,
    device: str,
    elapsed: float,
    doc_conversion: dict | None,
    docling_error: str,
) -> dict:
    """构造失败情况下的 meta 字典（避免重复代码）。"""
    return {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "sample_id": sample["id"],
        "sample_display_name": sample["display_name"],
        "source_path": sample["source_path"],
        "file_type": sample["file_type"],
        "device": device,
        "elapsed_seconds": elapsed,
        "doc_conversion": doc_conversion,
        "docling_error": docling_error,
        "export_results": {},
        "outputs": {},
    }


def process_sample(
    sample: dict,
    run_id: str,
    formats: list[str],
    device: str,
) -> dict:
    """
    对单份合同样本执行：路径解析 -> doc预转换（如需）-> Docling -> 多格式导出 -> 记录元数据。

    Returns:
        meta 字典（与 meta.json 内容一致），用于最终汇总报告。
    """
    sample_id = sample["id"]
    src_rel = sample["source_path"]
    src_path = PROJECT_ROOT / src_rel

    out_dir = OUTPUTS_DIR / run_id / sample_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  样本：{sample['display_name']} ({sample_id})")
    print(f"  源文件：{src_path}")
    print(f"{'='*60}")

    if not src_path.exists():
        msg = f"源文件不存在：{src_path}"
        print(f"  [错误] {msg}")
        meta = _make_failed_meta(sample, run_id, device, 0.0, None, msg)
        write_meta(out_dir, sample, run_id, device, 0.0, None, {}, msg)
        return meta

    # Step 1: .doc -> .docx（如需）
    doc_conversion_info: dict | None = None
    working_path = src_path

    if sample["file_type"] == "doc":
        print("  [预处理] 检测到 .doc 格式，尝试转换为 .docx ...")
        t0 = time.time()
        docx_path, method = convert_doc_to_docx(src_path, out_dir / "_converted")
        elapsed_conv = round(time.time() - t0, 2)
        if docx_path:
            print(f"  [预处理] 转换成功（{method}），耗时 {elapsed_conv}s")
            doc_conversion_info = {
                "success": True,
                "method": method,
                "elapsed_seconds": elapsed_conv,
                "output_path": str(docx_path),
            }
            working_path = docx_path
        else:
            print(f"  [警告] .doc 转换失败：{method}")
            doc_conversion_info = {"success": False, "error": method}
            meta = _make_failed_meta(sample, run_id, device, elapsed_conv, doc_conversion_info, "doc 预处理失败，跳过 Docling")
            write_meta(out_dir, sample, run_id, device, elapsed_conv, doc_conversion_info, {}, meta["docling_error"])
            return meta

    # Step 2: Docling 转换
    print(f"  [Docling] 开始转换（格式：{formats}，设备：{device}）...")
    t_start = time.time()
    document, docling_error = run_docling(working_path, device=device)
    elapsed = round(time.time() - t_start, 2)

    if docling_error:
        short = docling_error[:200]
        print(f"  [错误] Docling 转换失败（{elapsed}s）：{short}")
        meta = _make_failed_meta(sample, run_id, device, elapsed, doc_conversion_info, docling_error)
        write_meta(out_dir, sample, run_id, device, elapsed, doc_conversion_info, {}, docling_error)
        return meta

    print(f"  [Docling] 转换完成，耗时 {elapsed}s")

    # Step 3: 多格式导出
    print(f"  [导出] 写入格式：{formats}")
    export_results = export_formats(document, out_dir, formats)
    for fmt, status in export_results.items():
        tag = "OK" if status == "ok" else "FAIL"
        print(f"    [{tag}] .{fmt}: {status}")

    # Step 4: 元数据
    write_meta(out_dir, sample, run_id, device, elapsed, doc_conversion_info, export_results, "")

    return {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "sample_id": sample_id,
        "sample_display_name": sample["display_name"],
        "source_path": src_rel,
        "file_type": sample["file_type"],
        "device": device,
        "elapsed_seconds": elapsed,
        "doc_conversion": doc_conversion_info,
        "docling_error": "",
        "export_results": export_results,
        "outputs": {fmt: str(out_dir / f"output.{fmt}") for fmt, s in export_results.items() if s == "ok"},
    }


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Docling 合同格式保真度测试 — 将合同原文转换为 Markdown/HTML/JSON 并生成对比报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python convert.py                              # 全部样本，全部格式\n"
            "  python convert.py --sample-id 1-brand-venue   # 只转指定样本\n"
            "  python convert.py --formats md html           # 只导出 Markdown + HTML\n"
            "  python convert.py --device cpu                # 强制 CPU 推理\n"
        ),
    )
    parser.add_argument(
        "--sample-id",
        default=None,
        help="只转换指定样本（对应 samples.json 中的 id 字段），不指定则转换全部",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["md", "html", "json"],
        default=["md", "html", "json"],
        help="导出的目标格式，默认全部（md html json）",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["auto", "cpu", "cuda", "mps"],
        help="推理设备标记（记录用），默认 cpu",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="自定义运行 ID，不指定则自动生成时间戳 ID",
    )
    args = parser.parse_args()

    run_id = args.run_id or make_run_id()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'#'*60}")
    print(f"  Docling Contract Format Fidelity Test")
    print(f"  Run ID  : {run_id}")
    print(f"  Formats : {args.formats}")
    print(f"  Device  : {args.device}")
    print(f"  OutDir  : {OUTPUTS_DIR / run_id}")
    print(f"{'#'*60}\n")

    samples = load_samples(args.sample_id)
    print(f"Loaded {len(samples)} sample(s): {[s['id'] for s in samples]}\n")

    all_metas: list[dict] = []
    for sample in samples:
        meta = process_sample(sample, run_id, args.formats, args.device)
        all_metas.append(meta)

    summary = build_summary_report(run_id, all_metas)
    report_path = REPORTS_DIR / f"{run_id}_summary.md"
    report_path.write_text(summary, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  All done!")
    print(f"  Outputs    : {OUTPUTS_DIR / run_id}")
    print(f"  Report     : {report_path}")
    print(f"{'='*60}\n")
    print("Next steps:")
    print("  1. Open the summary report and fill in fidelity observations")
    print("  2. Append conclusions to experiment_log.md")
    print("  3. Use findings to decide v2 input format")


if __name__ == "__main__":
    main()
