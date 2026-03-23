from __future__ import annotations

import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


TERM_REPLACEMENTS = [
    ("local_llm", "本地模型"),
    ("third_party", "第三方平台"),
    ("Gold风险数", "标签风险数"),
    ("Pred风险数", "识别风险数"),
    ("Gold 风险点数", "标签风险点数"),
    ("Pred 风险点数", "识别风险点数"),
    ("Gold风险点", "标签风险点"),
    ("Pred风险点", "识别风险点"),
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
    parts = [p for p in normalized.split("/") if p]
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
                    # 计算段中允许空行，先跳过。
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


def _move_data_source_to_end(md_text: str) -> str:
    source_patterns = [
        re.compile(r"\n## 数据来源\n.*?(?=\n## |\Z)", re.S),
        re.compile(r"\n## 第三方平台主来源文件\n.*?(?=\n## |\Z)", re.S),
        re.compile(r"\n## third_party 主来源文件\n.*?(?=\n## |\Z)", re.S),
    ]

    source_block = ""
    body = md_text
    for pattern in source_patterns:
        m = pattern.search(body)
        if m:
            source_block = m.group(0)
            body = body[: m.start()] + "\n" + body[m.end() :]
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
            table_idx += 1
            header_cells = [c.strip() for c in line.strip("|").split("|")]
            header_text = "、".join(header_cells[:3])
            out.append(f"表{table_idx}：{header_text}（节选）")
            out.append("注：该表用于展示本节数据，指标定义见文末“指标说明”。")
        out.append(line)
        i += 1

    return "\n".join(out)


def process_markdown(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_paths(text)
    text = _replace_terms(text)
    text = _convert_metric_blocks_to_tables(text)
    text = _move_data_source_to_end(text)
    text = _add_table_titles(text)
    text = _ensure_glossary(text)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    for md_path in sorted(BASE_DIR.glob("*.md")):
        process_markdown(md_path)
    print("已完成 Markdown 客户版格式修正。")


if __name__ == "__main__":
    main()
