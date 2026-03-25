from __future__ import annotations

import argparse
import re
from pathlib import Path


SUMMARY_ROW_ORDER = [
    ("本地模型", "A"),
    ("本地模型", "B"),
    ("第三方平台", "A"),
    ("第三方平台", "B"),
]


TERM_REPLACEMENTS = [
    ("local_llm", "本地模型"),
    ("third_party", "第三方平台"),
    ("Gold风险数", "标签数"),
    ("Pred风险数", "预测数"),
    ("Gold 风险数", "标签数"),
    ("Pred 风险数", "预测数"),
    ("Gold风险点数", "标签风险点数"),
    ("Pred风险点数", "识别风险点数"),
    ("Gold 风险点数", "标签风险点数"),
    ("Pred 风险点数", "识别风险点数"),
    ("Gold风险点", "标签风险点"),
    ("Pred风险点", "识别风险点"),
    ("Gold 风险点", "标签风险点"),
    ("Pred 风险点", "识别风险点"),
    ("Explanation Structure Score", "解释结构完整度"),
    ("Suggestion Actionability Score", "建议可执行性"),
    ("Explanation Score", "解释结构完整度"),
    ("Suggestion Score", "建议可执行性"),
    ("Risk Precision", "风险点准确率"),
    ("Risk Recall", "风险点召回率"),
    ("Risk Miss Rate", "风险点漏报率"),
    ("Risk False Alarm Rate", "风险点误报率"),
    ("Risk F1", "风险点F1"),
    ("Clause Precision", "条款准确率"),
    ("Clause Recall", "条款召回率"),
    ("Clause Miss Rate", "条款漏报率"),
    ("Clause False Alarm Rate", "条款误报率"),
    ("Clause F1", "条款F1"),
]


def _shorten_path(path_str: str) -> str:
    value = path_str.strip().strip("`")
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return value

    idx = None
    for i, part in enumerate(parts):
        if re.match(r"^\d+-.*[\u4e00-\u9fff].*$", part):
            idx = i
            break
    if idx is None:
        for i, part in enumerate(parts):
            if re.search(r"[\u4e00-\u9fff]", part):
                idx = i
                break
    if idx is None:
        return value
    return "/".join(parts[idx:])


def _replace_paths(text: str) -> str:
    path_pattern = re.compile(r"[A-Za-z]:\\[^\n`<>\"]+")

    def repl(match: re.Match[str]) -> str:
        return _shorten_path(match.group(0))

    return path_pattern.sub(repl, text)


def _replace_terms(text: str) -> str:
    out = text
    for old, new in TERM_REPLACEMENTS:
        out = out.replace(old, new)
    return out


def _convert_metric_blocks_to_tables(md_text: str) -> str:
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.startswith("### ") and "计算过程" in line:
            metric_lines: list[str] = []
            j = i + 1
            while j < len(lines):
                cur = lines[j]
                if cur.startswith("### ") or cur.startswith("## "):
                    break
                if cur.startswith("| "):
                    break
                if cur.startswith("- "):
                    metric_lines.append(cur[2:].strip())
                    j += 1
                    continue
                if cur.strip() == "":
                    j += 1
                    continue
                break

            if metric_lines:
                while out and out[-1].strip() == "":
                    out.pop()
                out.append("")
                out.append("说明：下表为该口径的核心指标与公式，便于快速横向对比。")
                out.append("")
                out.append("| 指标项 | 数值 |")
                out.append("| --- | --- |")
                for metric in metric_lines:
                    if ":" in metric:
                        key, value = metric.split(":", 1)
                        out.append(f"| {key.strip()} | {value.strip()} |")
                    else:
                        out.append(f"| {metric.strip()} | - |")
                out.append("")
                i = j
                continue
        i += 1
    return "\n".join(out)


def _strip_ticks(value: str) -> str:
    return value.replace("`", "").strip()


def _extract_percent(text: str) -> str:
    values = re.findall(r"\d+(?:\.\d+)?%", text)
    return values[-1] if values else "-"


def _extract_tpfpfn(text: str) -> tuple[str, str, str]:
    numbers = re.findall(r"\d+", text)
    if len(numbers) >= 3:
        return numbers[0], numbers[1], numbers[2]
    return "-", "-", "-"


def _collect_summary_metrics(block: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    row_pattern = re.compile(r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", re.M)
    for key_raw, value_raw in row_pattern.findall(block):
        key = _strip_ticks(key_raw)
        value = _strip_ticks(value_raw)
        if key in {"指标项", "---"}:
            continue
        metrics[key] = value
    return metrics


def _metric_value(metrics: dict[str, str], *candidates: str) -> str:
    for key, value in metrics.items():
        for candidate in candidates:
            if candidate in key:
                return value if value and value != "-" else key
    return "-"


def _build_summary_rows(md_text: str) -> list[list[str]]:
    section_pattern = re.compile(
        r"###\s*(本地模型|第三方平台)\s*/\s*口径([AB]).*?计算过程\n(.*?)(?=\n### |\n## |\Z)",
        re.S,
    )

    found: dict[tuple[str, str], list[str]] = {}

    for model, scope, content in section_pattern.findall(md_text):
        metrics = _collect_summary_metrics(content)

        label_count = _metric_value(metrics, "标签风险点数", "标签数")
        pred_count = _metric_value(metrics, "识别风险点数", "预测数")

        tp_fp_fn_src = _metric_value(metrics, "风险点 TP / FP / FN")
        tp, fp, fn = _extract_tpfpfn(tp_fp_fn_src)

        precision = _extract_percent(_metric_value(metrics, "风险点 Precision", "风险点准确率"))
        recall = _extract_percent(_metric_value(metrics, "风险点 Recall", "风险点召回率"))
        miss_rate = _extract_percent(_metric_value(metrics, "风险点 Miss Rate", "风险点漏报率"))
        false_alarm = _extract_percent(_metric_value(metrics, "风险点 False Alarm Rate", "风险点误报率"))
        f1 = _extract_percent(_metric_value(metrics, "风险点 F1"))

        found[(model, scope)] = [
            f"{model}·口径{scope}",
            label_count,
            pred_count,
            tp,
            fp,
            fn,
            precision,
            recall,
            miss_rate,
            false_alarm,
            f1,
        ]

    rows: list[list[str]] = []
    for key in SUMMARY_ROW_ORDER:
        if key in found:
            rows.append(found[key])
    return rows


def _insert_or_replace_summary_table(md_text: str) -> str:
    rows = _build_summary_rows(md_text)
    if not rows:
        return md_text

    summary_lines = [
        "## 指标对比汇总表",
        "",
        "表0：模型/口径、标签数、预测数、TP/FP/FN、准确率、召回率等对照",
        "注：下表为各模型在不同评价口径下的关键指标对比，便于快速评估识别效果。",
        "",
        "| 模型/口径 | 标签数 | 预测数 | 风险点TP | 风险点FP | 风险点FN | 精确率 | 召回率 | 漏报率 | 误报率 | F1得分 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        summary_lines.append("| " + " | ".join(row) + " |")
    summary = "\n".join(summary_lines) + "\n\n"

    existing = re.compile(r"\n## 指标对比汇总表\n.*?(?=\n## )", re.S)
    if existing.search(md_text):
        return existing.sub("\n" + summary, md_text, count=1)

    marker = "\n## 原文 / 本地模型 / 第三方平台 / 采纳说明 并行对照"
    if marker in md_text:
        return md_text.replace(marker, "\n" + summary + marker, 1)

    return summary + md_text


def _insert_overall_exec_summary(md_text: str) -> str:
    """Insert a standardized executive summary for overall report files."""
    if "总体汇总与计算过程" not in md_text:
        return md_text

    summary_lines = [
        "## 总结",
        "",
        "经过格式验证，当前流程可将原始 `doc/docx` 合同稳定转换为 `md`，并用于模型交互与风险评测。",
        "",
        "风险评测分为两种口径：",
        "- `口径A`：将采纳情况说明中的“采纳”“部分采纳”作为正样本标签。",
        "- `口径B`：将采纳情况说明中的“采纳”“部分采纳”“未采纳”均作为正样本标签，近似第三方识别出的风险集合。",
        "",
        "两种口径下，分别对第三方平台与仅依靠提示词的本地模型进行条款级与风险点级评估，核心指标包括准确率、召回率、漏报率、误报率。",
        "",
        "从当前总体结果看：",
        "- 条款识别层面：本地模型准确率整体略低于第三方平台。",
        "- 风险点识别层面：在口径A（贴近人工审查标准）下，本地模型准确率与召回率均偏低，需后续重点优化。",
        "",
        "结果解释与使用边界：",
        "- 当前样本量较小，结论仅可作为阶段性参考。",
        "- 现有真实值“采纳情况说明”来自第三方审查结果的筛选，因此第三方在现阶段会出现较高召回（部分场景接近或达到100%）。",
        "- 若希望召回率成为更公平、可比较的指标，后续需补充“第三方未检出但人工确认存在”的风险点样本。",
        "",
    ]
    summary_block = "\n".join(summary_lines)

    existing = re.compile(r"\n## (?:执行摘要|总结)\n.*?(?=\n## )", re.S)
    if existing.search(md_text):
        return existing.sub("\n" + summary_block, md_text, count=1)

    title_match = re.search(r"^# .*?\n", md_text, re.M)
    if not title_match:
        return summary_block + "\n" + md_text

    insert_pos = title_match.end()
    return md_text[:insert_pos] + "\n" + summary_block + md_text[insert_pos:]


def _move_data_source_to_end(md_text: str) -> str:
    source_patterns = [
        re.compile(r"\n## 数据来源\n.*?(?=\n## |\Z)", re.S),
        re.compile(r"\n## 第三方平台主来源文件\n.*?(?=\n## |\Z)", re.S),
        re.compile(r"\n## third_party 主来源文件\n.*?(?=\n## |\Z)", re.S),
    ]

    source_block = ""
    body = md_text
    for pattern in source_patterns:
        matched = pattern.search(body)
        if matched:
            source_block = matched.group(0)
            body = body[: matched.start()] + "\n" + body[matched.end() :]
            break

    if not source_block:
        return body

    source_block = source_block.replace("## third_party 主来源文件", "## 数据来源（相对路径参考）")
    source_block = source_block.replace("## 第三方平台主来源文件", "## 数据来源（相对路径参考）")
    source_block = source_block.replace("## 数据来源", "## 数据来源（相对路径参考）")

    extra_note = "\n说明：数据来源用于追溯，展示中仅保留相对路径作为参考。\n"
    body = body.rstrip() + "\n" + source_block.rstrip() + extra_note + "\n"
    return body


def _ensure_glossary(md_text: str) -> str:
    marker = "## 指标说明"
    if marker not in md_text:
        md_text += "\n\n## 指标说明\n"

    additions = [
        "- `口径A`：仅统计采纳与部分采纳的标签（accept + partial）。",
        "- `口径B`：统计采纳说明中的全部标签。",
        "- `标签数`：当前口径下人工标签总数。",
        "- `预测数`：当前参与方识别结果总数。",
        "- `标签风险点数`：人工审查标签中的风险点总数。",
        "- `识别风险点数`：当前参与方识别出的风险点总数。",
        "- `TP / FP / FN`：分别表示命中、误报、漏报。",
    ]

    for item in additions:
        if item not in md_text:
            md_text += "\n" + item
    return md_text


def _add_table_titles(md_text: str) -> str:
    lines = md_text.splitlines()
    out: list[str] = []
    table_idx = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("| ") and i + 1 < len(lines) and lines[i + 1].startswith("| ---"):
            # Remove previously injected title/note lines so reruns are idempotent.
            while out and out[-1].strip() == "":
                out.pop()
            while out and (
                re.match(r"^表\d+：", out[-1].strip())
                or out[-1].strip().startswith("注：该表用于展示本节数据")
            ):
                out.pop()
                while out and out[-1].strip() == "":
                    out.pop()

            prev_nonempty = ""
            for prev in reversed(out):
                if prev.strip():
                    prev_nonempty = prev.strip()
                    break

            is_summary_table = prev_nonempty.startswith("注：下表为各模型在不同评价口径下的关键指标对比")
            if not is_summary_table:
                table_idx += 1
                header_cells = [cell.strip() for cell in line.strip("|").split("|")]
                header_text = "、".join(header_cells[:3])
                out.append(f"表{table_idx}：{header_text}（节选）")
                out.append("注：该表用于展示本节数据，指标定义见文末“指标说明”。")
        out.append(line)
        i += 1

    return "\n".join(out)


def format_markdown_text(text: str) -> str:
    formatted = text
    formatted = _replace_paths(formatted)
    formatted = _replace_terms(formatted)
    formatted = _insert_overall_exec_summary(formatted)
    formatted = _convert_metric_blocks_to_tables(formatted)
    formatted = _insert_or_replace_summary_table(formatted)
    formatted = _move_data_source_to_end(formatted)
    formatted = _add_table_titles(formatted)
    formatted = _ensure_glossary(formatted)
    return formatted


def process_markdown(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(format_markdown_text(text), encoding="utf-8")


def process_markdown_dir(base_dir: Path) -> list[Path]:
    files = sorted(base_dir.glob("*.md"))
    for md_path in files:
        process_markdown(md_path)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Format parallel reports for customer-friendly output")
    parser.add_argument(
        "--dir",
        default=".",
        help="Directory containing report markdown files",
    )
    args = parser.parse_args()

    base_dir = Path(args.dir).resolve()
    files = process_markdown_dir(base_dir)
    print(f"已完成 Markdown 客户版格式修正，共 {len(files)} 个文件。")


if __name__ == "__main__":
    main()
