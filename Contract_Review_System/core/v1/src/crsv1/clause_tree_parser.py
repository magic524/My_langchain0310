from __future__ import annotations

import re
from dataclasses import asdict

from .runtime_types import ClauseNode, ClauseReviewTask
from .text_utils import compact_text, short_preview


ARTICLE_TOP_RE = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[条章节编部部分])\s*(.*)$")
TOP_CHINESE_RE = re.compile(r"^([一二三四五六七八九十百千]+[、.．])\s*(.*)$")
TOP_ARABIC_RE = re.compile(r"^(\d+)[、.．]\s*(.*)$")
DECIMAL_RE = re.compile(r"^(\d+(?:\.\d+)+)[、.．]?\s*(.*)$")
PAREN_ZH_RE = re.compile(r"^[（(]([一二三四五六七八九十百千]+)[）)]\s*(.*)$")
PAREN_NUM_RE = re.compile(r"^[（(](\d+)[）)]\s*(.*)$")
BOLD_RE = re.compile(r"^\*\*(.+?)\*\*$")


def _clean_line(line: str) -> str:
    # 去掉空行和图片占位行，避免影响条款结构识别。
    stripped = line.strip()
    if not stripped or stripped == "<!-- image -->":
        return ""
    return compact_text(stripped)


def _match_heading(line: str) -> tuple[str, str, str]:
    """识别一行是否为标题，并返回标题类型、标题文本、编号标记。"""

    if line.startswith("#"):
        return "markdown_heading", line.lstrip("#").strip(), ""

    matched = BOLD_RE.match(line)
    if matched:
        return "bold_heading", matched.group(1).strip(), ""

    matched = ARTICLE_TOP_RE.match(line)
    if matched:
        suffix = matched.group(2).strip()
        heading = matched.group(1).strip()
        if suffix:
            heading = f"{heading} {suffix}".strip()
        return "article_top", heading, ""

    matched = TOP_CHINESE_RE.match(line)
    if matched:
        return "chinese_top", line, matched.group(1).strip()

    matched = DECIMAL_RE.match(line)
    if matched:
        return "arabic_decimal", line, matched.group(1).strip()

    matched = TOP_ARABIC_RE.match(line)
    if matched:
        return "arabic_item", line, matched.group(1).strip()

    matched = PAREN_ZH_RE.match(line)
    if matched:
        return "paren_chinese", line, matched.group(1).strip()

    matched = PAREN_NUM_RE.match(line)
    if matched:
        return "paren_numeric", line, matched.group(1).strip()

    return "", "", ""


def _extract_leading_arabic_token(text: str) -> str:
    matched = re.match(r"^(\d+(?:\.\d+)*)", text.strip())
    return matched.group(1) if matched else ""


def _resolve_heading_level(
    heading_type: str,
    marker: str,
    stack: list[ClauseNode],
    previous_heading_type: str,
) -> int:
    """根据编号样式和局部上下文推断层级。"""

    if heading_type in {"bold_heading", "article_top", "chinese_top", "preface_top"}:
        # 顶层标题直接归为一级。
        return 1

    if heading_type == "arabic_item":
        # 阿拉伯编号可能是一级也可能是二级，这里结合父栈和前一标题类型判定。
        parent_heading_types = {node.heading_type for node in stack[1:]}
        if parent_heading_types & {"bold_heading", "article_top", "chinese_top", "preface_top"}:
            return 2
        if previous_heading_type in {"chinese_top", "arabic_child"}:
            return 2
        return 1

    if heading_type == "arabic_decimal":
        # 形如 1.2.3 的层级通常由小数段数决定，同时尝试贴近最近父级语境。
        segments = marker.split(".")
        if len(segments) == 1:
            return 2
        integer_part = segments[0]
        for node in reversed(stack[1:]):
            token = _extract_leading_arabic_token(node.heading)
            if token == integer_part and node.heading_type in {"arabic_item", "arabic_child"}:
                return node.level + len(segments) - 1
        return len(segments)

    if heading_type == "paren_chinese":
        return 2

    if heading_type == "paren_numeric":
        return 3

    return -1


def _normalize_heading_type(heading_type: str, level: int) -> str:
    if heading_type == "arabic_item" and level >= 2:
        return "arabic_child"
    return heading_type


def _finalize_node(node: ClauseNode) -> None:
    # 每个节点最终文本 = 标题 + 正文，供后续提示词和报告直接使用。
    body = "\n".join(node.body_lines).strip()
    node.full_text = "\n".join(part for part in [node.heading.strip(), body] if part).strip()
    if not node.full_text:
        node.full_text = node.heading.strip()


def _make_preface_node(contract_id: str, node_id: str, lines: list[str], line_end: int) -> ClauseNode:
    node = ClauseNode(
        node_id=node_id,
        contract_id=contract_id,
        level=1,
        heading="前言与合同主体",
        heading_type="preface_top",
        parent_id=f"{contract_id}__root",
        line_start=1,
        line_end=max(line_end, 1),
        body_lines=list(lines),
    )
    _finalize_node(node)
    return node


def parse_clause_tree(contract_id: str, markdown_text: str) -> list[ClauseNode]:
    """将合同 Markdown 解析为条款树。"""

    cleaned_lines = [
        (index, _clean_line(raw_line))
        for index, raw_line in enumerate(markdown_text.splitlines(), start=1)
    ]
    cleaned_lines = [(index, line) for index, line in cleaned_lines if line]

    root = ClauseNode(
        node_id=f"{contract_id}__root",
        contract_id=contract_id,
        level=0,
        heading="ROOT",
        heading_type="root",
        parent_id="",
        line_start=1,
        line_end=1,
    )
    stack: list[ClauseNode] = [root]
    node_counter = 0
    previous_heading_type = ""
    preface_lines: list[str] = []
    preface_end_line = 1

    for line_no, line in cleaned_lines:
        heading_type, heading, marker = _match_heading(line)
        if heading_type == "markdown_heading":
            continue

        if heading_type:
            level = _resolve_heading_level(heading_type, marker, stack, previous_heading_type)
            normalized_heading_type = _normalize_heading_type(heading_type, level)

            # 通过栈回退找到当前标题的父节点。
            while len(stack) > 1 and stack[-1].level >= level:
                _finalize_node(stack.pop())

            parent = stack[-1]
            node_counter += 1
            node = ClauseNode(
                node_id=f"{contract_id}_n{node_counter:03d}",
                contract_id=contract_id,
                level=level,
                heading=heading or short_preview(line, limit=32),
                heading_type=normalized_heading_type,
                parent_id=parent.node_id,
                line_start=line_no,
                line_end=line_no,
                body_lines=[],
            )
            parent.children.append(node)
            stack.append(node)
            previous_heading_type = normalized_heading_type
            continue

        current = stack[-1]
        if current is root:
            # 根节点正文当作前言候选，在最后补成“前言与合同主体”节点。
            preface_lines.append(line)
            preface_end_line = line_no
            continue
        current.body_lines.append(line)
        current.line_end = line_no

    while len(stack) > 1:
        _finalize_node(stack.pop())

    if preface_lines:
        node_counter += 1
        preface_node = _make_preface_node(
            contract_id,
            f"{contract_id}_n{node_counter:03d}",
            preface_lines,
            preface_end_line,
        )
        root.children.insert(0, preface_node)

    root.body_lines = preface_lines
    _finalize_node(root)

    if not root.children:
        # 极端情况下未识别到任何标题，退化为“全文条款”单节点，避免后续流程中断。
        synthetic = ClauseNode(
            node_id=f"{contract_id}_n001",
            contract_id=contract_id,
            level=1,
            heading=short_preview(root.full_text or markdown_text, limit=24) or "全文条款",
            heading_type="synthetic_top",
            parent_id=root.node_id,
            line_start=1,
            line_end=max((line_no for line_no, _ in cleaned_lines), default=1),
            body_lines=[root.full_text or markdown_text],
        )
        _finalize_node(synthetic)
        root.children.append(synthetic)

    return root.children


def iter_clause_nodes(nodes: list[ClauseNode]) -> list[ClauseNode]:
    """按先序遍历展开条款树。"""

    ordered: list[ClauseNode] = []
    for node in nodes:
        ordered.append(node)
        ordered.extend(iter_clause_nodes(node.children))
    return ordered


def build_review_tasks(contract_id: str, clause_tree: list[ClauseNode]) -> list[ClauseReviewTask]:
    """以顶层父条款为单位构造审查任务。"""

    tasks: list[ClauseReviewTask] = []
    for index, node in enumerate(clause_tree, start=1):
        # 子条款会拼入同一个任务上下文，便于模型做父-子条款一致性判断。
        child_nodes = iter_clause_nodes(node.children)
        prompt_lines = [
            f"父条款标题：{node.heading}",
            "父条款全文：",
            node.full_text,
        ]
        if child_nodes:
            prompt_lines.append("子条款列表：")
            for child in child_nodes:
                prompt_lines.append(f"- {child.node_id} {child.heading}")
                prompt_lines.append(child.full_text)
        tasks.append(
            ClauseReviewTask(
                task_id=f"{contract_id}_task_{index:03d}",
                contract_id=contract_id,
                parent_clause_id=node.node_id,
                parent_heading=node.heading,
                prompt_text="\n".join(part for part in prompt_lines if part).strip(),
                child_clause_ids=[child.node_id for child in child_nodes],
                child_clause_headings=[child.heading for child in child_nodes],
            )
        )
    return tasks


def serialize_clause_tree(nodes: list[ClauseNode]) -> list[dict]:
    """将条款树序列化为普通字典结构。"""

    return [asdict(node) for node in nodes]
