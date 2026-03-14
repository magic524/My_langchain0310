from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.documents import Document

try:
    from langchain_community.document_loaders import Docx2txtLoader
except Exception:
    Docx2txtLoader = None  # type: ignore[assignment]

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
REVIEW_DIR_KEYWORDS = (
    "review",
    "comment",
    "comments",
    "revision",
    "revisions",
    "annotate",
    "annotated",
    "审查",
    "批注",
    "修订",
)

SYSTEM_PROMPT = """你是一名严谨的合同审查助手。

你的任务不是泛泛而谈，而是学习参考知识库中的“批注风格、审查重点、修订表达方式”，
然后对新的合同条款给出同风格的审查意见。

输出要求：
1. 只基于目标条款和给定参考材料输出，不要虚构法律事实。
2. 如果该条款没有明显可审查问题，只输出：无需批注
3. 如果需要审查，请严格按下面的 Markdown 结构输出：

风险级别：高 / 中 / 低
问题说明：用 1-3 句话说明风险或歧义
审查批注：写成可直接贴给业务或法务的批注口吻
建议修改：给出可执行的修改建议，必要时可直接给替换文本
参考依据：列出你主要参考的历史批注/修订要点，不要编造文件名

4. 输出必须简洁、具体，避免空泛套话。
5. 如果参考材料不足以支撑明确判断，可以指出“参考不足”。
6. 必须使用中文输出，禁止输出英文思维过程、`Thinking Process`、`<think>` 或任何推理草稿。
"""


@dataclass(slots=True)
class ParsedWordFile:
    """解析后的 Word 文件内容。"""

    path: Path
    file_type: str
    role: str
    text: str
    paragraphs: list[str]
    comments: list[str]
    revisions: list[str]


@dataclass(slots=True)
class RuntimeConfig:
    """运行时模型配置。"""

    model_name: str
    model_provider: str
    temperature: float
    api_key: str
    base_url: str | None
    extra_body: dict[str, Any] | None


class DocExtractionUnavailableError(RuntimeError):
    """当前环境无法解析旧版 .doc 文件。"""


def _parse_json_env(env_name: str) -> dict[str, Any] | None:
    raw_value = os.getenv(env_name)
    if not raw_value:
        return None

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        msg = f"环境变量 {env_name} 不是合法 JSON：{exc}"
        raise ValueError(msg) from exc

    if not isinstance(parsed, dict):
        msg = f"环境变量 {env_name} 必须是 JSON 对象。"
        raise ValueError(msg)
    return parsed


def _parse_temperature(raw_value: str | None, *, default: float) -> float:
    if raw_value is None or not raw_value.strip():
        return default

    try:
        return float(raw_value)
    except ValueError as exc:
        msg = f"环境变量 OPENAI_TEMPERATURE 不是合法数字：{raw_value}"
        raise ValueError(msg) from exc


def configure_runtime_env() -> RuntimeConfig:
    """加载 .env 并构造 OpenAI 兼容模型配置。"""

    load_dotenv(find_dotenv())

    model_name = (
        os.getenv("OPENAI_LLM_MODEL")
        or os.getenv("OPENAI_MODEL_NAME")
        or os.getenv("OPENAI_MODEL")
    )
    model_provider = os.getenv("OPENAI_MODEL_PROVIDER", "openai")
    openai_api_base = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    extra_body = _parse_json_env("OPENAI_EXTRA_BODY")
    temperature = _parse_temperature(os.getenv("OPENAI_TEMPERATURE"), default=0.0)

    if dashscope_api_key and not openai_api_key:
        openai_api_key = dashscope_api_key

    if openai_api_base and not openai_api_key:
        openai_api_key = "EMPTY"

    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key

    if openai_api_base:
        os.environ.setdefault("OPENAI_API_BASE", openai_api_base)
        os.environ.setdefault("OPENAI_BASE_URL", openai_api_base)

    if not openai_api_base and (openai_api_key or "").strip().upper() == "EMPTY":
        msg = (
            "检测到 OPENAI_API_KEY=EMPTY 但未配置 OPENAI_API_BASE/OPENAI_BASE_URL。"
            "这会请求官方 OpenAI 并触发 401。"
            "请为本地 LLM 设置 OPENAI_API_BASE（例如 http://host:port/v1）。"
        )
        raise RuntimeError(msg)

    if not model_name:
        model_name = "qwen-plus"

    return RuntimeConfig(
        model_name=model_name,
        model_provider=model_provider,
        temperature=temperature,
        api_key=openai_api_key or "EMPTY",
        base_url=openai_api_base,
        extra_body=extra_body,
    )


def infer_file_role(path: Path, root_dir: Path) -> str:
    """根据路径推断文件在知识库中的角色。"""

    try:
        relative_parts = [part.lower() for part in path.relative_to(root_dir).parts]
    except ValueError:
        relative_parts = [part.lower() for part in path.parts]

    if any(keyword in part for part in relative_parts for keyword in REVIEW_DIR_KEYWORDS):
        return "review"
    return "original"


def normalize_whitespace(text: str) -> str:
    """压缩空白字符，保留段落边界。"""

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    cleaned_lines = [line for line in lines if line]
    return "\n".join(cleaned_lines)


def paragraph_text(paragraph: ET.Element) -> str:
    """提取单个段落中的可见文字。"""

    parts: list[str] = []
    for node in paragraph.findall(".//w:t", WORD_NS):
        if node.text:
            parts.append(node.text)
    return normalize_whitespace("".join(parts))


def extract_docx_paragraphs_with_docx2txt(path: Path) -> list[str]:
    """使用 Docx2txtLoader 提取正文段落。"""

    if Docx2txtLoader is None:
        return []

    loader = Docx2txtLoader(str(path))
    try:
        documents = loader.load()
    except ModuleNotFoundError as exc:
        if exc.name == "docx2txt":
            return []
        raise
    if not documents:
        return []

    text = normalize_whitespace("\n".join(doc.page_content for doc in documents))
    if not text:
        return []

    paragraphs = [normalize_whitespace(part) for part in text.split("\n")]
    return [paragraph for paragraph in paragraphs if paragraph]


def extract_docx(path: Path, role: str) -> ParsedWordFile:
    """提取 .docx 中的正文、批注和修订信息。"""

    paragraphs = extract_docx_paragraphs_with_docx2txt(path)
    comments: list[str] = []
    revisions: list[str] = []

    with zipfile.ZipFile(path) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
        if not paragraphs:
            for paragraph in document_root.findall(".//w:p", WORD_NS):
                text = paragraph_text(paragraph)
                if text:
                    paragraphs.append(text)

        for ins in document_root.findall(".//w:ins", WORD_NS):
            inserted = "".join(node.text or "" for node in ins.findall(".//w:t", WORD_NS))
            inserted = normalize_whitespace(inserted)
            if inserted:
                revisions.append(f"插入：{inserted}")

        for deletion in document_root.findall(".//w:del", WORD_NS):
            deleted = "".join(node.text or "" for node in deletion.findall(".//w:delText", WORD_NS))
            deleted = normalize_whitespace(deleted)
            if deleted:
                revisions.append(f"删除：{deleted}")

        if "word/comments.xml" in archive.namelist():
            comments_root = ET.fromstring(archive.read("word/comments.xml"))
            for comment_node in comments_root.findall(".//w:comment", WORD_NS):
                author = comment_node.attrib.get(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author",
                    "未知作者",
                )
                comment_parts: list[str] = []
                for paragraph in comment_node.findall(".//w:p", WORD_NS):
                    text = paragraph_text(paragraph)
                    if text:
                        comment_parts.append(text)
                joined_comment = normalize_whitespace("\n".join(comment_parts))
                if joined_comment:
                    comments.append(f"{author}：{joined_comment}")

    full_text = "\n".join(paragraphs)
    return ParsedWordFile(
        path=path,
        file_type="docx",
        role=role,
        text=full_text,
        paragraphs=paragraphs,
        comments=comments,
        revisions=revisions,
    )


def _looks_meaningful_text(line: str) -> bool:
    if len(line.strip()) < 8:
        return False
    meaningful = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", line)
    return len(meaningful) >= max(5, len(line) // 4)


def _convert_doc_to_docx_with_word(path: Path) -> Path | None:
    if os.name != "nt":
        return None

    try:
        pythoncom = importlib.import_module("pythoncom")
        win32com_client = importlib.import_module("win32com.client")
    except ImportError:
        return None

    temp_dir = Path(tempfile.mkdtemp(prefix="contract-review-doc-"))
    docx_path = temp_dir / f"{path.stem}.docx"
    word = None
    document = None
    pythoncom.CoInitialize()
    try:
        word = win32com_client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(path), ReadOnly=True)
        document.SaveAs(str(docx_path), FileFormat=16)
        return docx_path
    except Exception:
        if docx_path.exists():
            docx_path.unlink(missing_ok=True)
        temp_dir.rmdir()
        return None
    finally:
        if document is not None:
            document.Close(False)
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()


def _convert_doc_to_docx_with_soffice(path: Path) -> Path | None:
    soffice_cmd = shutil.which("soffice")
    if soffice_cmd is None:
        return None

    temp_dir = Path(tempfile.mkdtemp(prefix="contract-review-doc-"))
    completed = subprocess.run(
        [
            soffice_cmd,
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(temp_dir),
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        temp_dir.rmdir()
        return None

    docx_path = temp_dir / f"{path.stem}.docx"
    if not docx_path.exists():
        temp_dir.rmdir()
        return None
    return docx_path


def _extract_doc_via_converted_docx(path: Path, role: str) -> ParsedWordFile | None:
    converted_path = _convert_doc_to_docx_with_word(path)
    if converted_path is None:
        converted_path = _convert_doc_to_docx_with_soffice(path)
    if converted_path is None:
        return None

    try:
        parsed = extract_docx(converted_path, role)
    finally:
        converted_path.unlink(missing_ok=True)
        converted_path.parent.rmdir()

    return ParsedWordFile(
        path=path,
        file_type="doc",
        role=role,
        text=parsed.text,
        paragraphs=parsed.paragraphs,
        comments=parsed.comments,
        revisions=parsed.revisions,
    )


def extract_doc_best_effort(path: Path, role: str) -> ParsedWordFile:
    """尽力从旧版 .doc 提取文本。"""

    converted = _extract_doc_via_converted_docx(path, role)
    if converted is not None:
        return ParsedWordFile(
            path=path,
            file_type="doc",
            role=role,
            text=converted.text,
            paragraphs=converted.paragraphs,
            comments=converted.comments,
            revisions=converted.revisions,
        )

    strings_cmd = shutil.which("strings")
    if strings_cmd is None:
        msg = (
            "当前环境无法解析旧版 .doc 文件：未检测到 Microsoft Word、LibreOffice soffice "
            "或 strings 命令。请安装 pywin32 并确保本机可调用 Word，或先把文件转成 .docx。"
        )
        raise DocExtractionUnavailableError(msg)

    completed = subprocess.run(
        [strings_cmd, "-n", "8", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        msg = f"读取 .doc 文件失败：{path}"
        raise RuntimeError(msg)

    raw_lines = completed.stdout.splitlines()
    paragraphs = [normalize_whitespace(line) for line in raw_lines if _looks_meaningful_text(line)]
    unique_paragraphs: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        if paragraph and paragraph not in seen:
            unique_paragraphs.append(paragraph)
            seen.add(paragraph)

    return ParsedWordFile(
        path=path,
        file_type="doc",
        role=role,
        text="\n".join(unique_paragraphs),
        paragraphs=unique_paragraphs,
        comments=[],
        revisions=[],
    )


def parse_word_file(path: Path, role: str) -> ParsedWordFile:
    """根据扩展名选择解析方式。"""

    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path, role)
    if suffix == ".doc":
        return extract_doc_best_effort(path, role)
    msg = f"不支持的文件类型：{path}"
    raise ValueError(msg)


def iter_word_files(root_dir: Path) -> list[Path]:
    """递归列出目录下所有 doc/docx 文件。"""

    paths = [path for path in root_dir.rglob("*") if path.suffix.lower() in {".doc", ".docx"}]
    return sorted(path for path in paths if path.is_file())


def build_knowledge_documents(parsed_files: Sequence[ParsedWordFile]) -> list[Document]:
    """把解析结果转换成轻量检索文档。"""

    documents: list[Document] = []
    for parsed in parsed_files:
        for index, paragraph in enumerate(parsed.paragraphs, start=1):
            if len(paragraph) < 20:
                continue
            documents.append(
                Document(
                    page_content=paragraph,
                    metadata={
                        "source": str(parsed.path),
                        "role": parsed.role,
                        "kind": "paragraph",
                        "index": index,
                    },
                )
            )

        for index, comment in enumerate(parsed.comments, start=1):
            documents.append(
                Document(
                    page_content=comment,
                    metadata={
                        "source": str(parsed.path),
                        "role": parsed.role,
                        "kind": "comment",
                        "index": index,
                    },
                )
            )

        for index, revision in enumerate(parsed.revisions, start=1):
            documents.append(
                Document(
                    page_content=revision,
                    metadata={
                        "source": str(parsed.path),
                        "role": parsed.role,
                        "kind": "revision",
                        "index": index,
                    },
                )
            )

    return documents


def tokenize_text(text: str) -> Counter[str]:
    """针对中英文混合文本的简易分词。"""

    counter: Counter[str] = Counter()
    for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        if re.fullmatch(r"[A-Za-z0-9_]+", token):
            if len(token) >= 2:
                counter[token] += 1
            continue

        if len(token) == 1:
            counter[token] += 1
            continue

        for size in (2, 3):
            if len(token) < size:
                continue
            for index in range(len(token) - size + 1):
                counter[token[index : index + size]] += 1
    return counter


def reference_weight(document: Document) -> float:
    """给批注和审查材料更高权重。"""

    kind = str(document.metadata.get("kind", "paragraph"))
    role = str(document.metadata.get("role", "original"))

    weight = 1.0
    if role == "review":
        weight += 0.8
    if kind == "comment":
        weight += 1.2
    elif kind == "revision":
        weight += 0.9
    return weight


def score_document(query: str, document: Document) -> float:
    """按关键词重叠和材料类型进行打分。"""

    query_tokens = tokenize_text(query)
    document_tokens = tokenize_text(document.page_content)
    if not query_tokens or not document_tokens:
        return 0.0

    overlap_score = 0.0
    for token, count in query_tokens.items():
        overlap_score += min(count, document_tokens.get(token, 0))

    if not overlap_score:
        return 0.0

    query_compact = normalize_whitespace(query)
    doc_compact = normalize_whitespace(document.page_content)
    phrase_bonus = 0.0
    if query_compact and query_compact[:24] in doc_compact:
        phrase_bonus += 3.0
    if doc_compact and doc_compact[:24] in query_compact:
        phrase_bonus += 2.0

    return (overlap_score + phrase_bonus) * reference_weight(document)


def retrieve_references(query: str, knowledge_documents: Sequence[Document], top_k: int) -> list[Document]:
    """从知识库中取最相关的参考材料。"""

    scored: list[tuple[float, Document]] = []
    for document in knowledge_documents:
        score = score_document(query, document)
        if score > 0:
            scored.append((score, document))

    scored.sort(
        key=lambda item: (
            item[0],
            1 if item[1].metadata.get("role") == "review" else 0,
            1 if item[1].metadata.get("kind") == "comment" else 0,
        ),
        reverse=True,
    )
    return [document for _, document in scored[:top_k]]


def select_target_paragraphs(parsed: ParsedWordFile, max_paragraphs: int, min_chars: int) -> list[str]:
    """筛选待审查段落。"""

    selected: list[str] = []
    seen: set[str] = set()
    for paragraph in parsed.paragraphs:
        compact = normalize_whitespace(paragraph)
        if len(compact) < min_chars or compact in seen:
            continue
        selected.append(compact)
        seen.add(compact)
        if len(selected) >= max_paragraphs:
            break
    return selected


def truncate_text(text: str, limit: int) -> str:
    """按字符截断长文本。"""

    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def format_references(references: Sequence[Document]) -> str:
    """将检索到的参考材料格式化到 prompt 中。"""

    lines: list[str] = []
    for index, reference in enumerate(references, start=1):
        source = str(reference.metadata.get("source", "未知来源"))
        kind = str(reference.metadata.get("kind", "paragraph"))
        role = str(reference.metadata.get("role", "original"))
        content = truncate_text(reference.page_content, 280)
        lines.append(f"[{index}] 角色={role}; 类型={kind}; 来源={source}\n{content}")
    return "\n\n".join(lines)


def ai_message_to_text(response: object) -> str:
    """兼容不同消息内容结构。"""

    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part.strip() for part in parts if part.strip()).strip()
    return str(content).strip()


def sanitize_review_text(text: str) -> str:
    """清洗模型输出，只保留最终可展示的中文审查内容。"""

    cleaned = text.strip()
    if not cleaned:
        return cleaned

    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)

    risk_markers = ("风险级别：", "风险级别:")
    no_comment_markers = ("无需批注",)
    final_markers = [
        *(cleaned.find(marker) for marker in risk_markers if marker in cleaned),
        *(cleaned.find(marker) for marker in no_comment_markers if marker in cleaned),
    ]
    if final_markers:
        cleaned = cleaned[min(final_markers) :]

    cleaned = re.sub(r"^Thinking\s+Process:.*", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = cleaned.strip()

    if "风险级别" not in cleaned and "无需批注" in cleaned:
        return "无需批注"
    return cleaned


def review_single_paragraph(model: Any, paragraph: str, references: Sequence[Document]) -> str:
    """对单个条款生成批注式审查意见。"""

    reference_text = format_references(references) if references else "无"
    human_prompt = (
        "请参考下面的历史审查材料，对目标条款进行同风格审查。\n\n"
        "请仅输出中文最终审查结果，不要输出思考过程、英文说明或 `<think>` 内容。\n\n"
        f"目标条款：\n{paragraph}\n\n"
        f"参考材料：\n{reference_text}\n"
    )
    response = model.invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("human", human_prompt),
        ]
    )
    return sanitize_review_text(ai_message_to_text(response))


def build_report(
    target_file: ParsedWordFile,
    review_sections: Sequence[tuple[str, str, Sequence[Document]]],
    knowledge_files: Sequence[ParsedWordFile],
) -> str:
    """生成 Markdown 审查报告。"""

    total_comments = sum(len(item.comments) for item in knowledge_files)
    total_revisions = sum(len(item.revisions) for item in knowledge_files)

    lines = [
        "# 合同审查报告",
        "",
        f"- 待审文件：{target_file.path}",
        f"- 待审文件类型：{target_file.file_type}",
        f"- 知识库文件数：{len(knowledge_files)}",
        f"- 历史批注数：{total_comments}",
        f"- 历史修订痕迹数：{total_revisions}",
        "",
        "## 说明",
        "",
        "本报告依据知识库中的原合同、批注、修订材料生成，当前版本输出为 Markdown 审查建议，便于后续再接入 Word 批注回写。",
        "",
        "## 审查结果",
        "",
    ]

    if not review_sections:
        lines.append("未识别出明确需要批注的条款，或知识库参考材料不足。")
        return "\n".join(lines)

    for index, (paragraph, review_text, references) in enumerate(review_sections, start=1):
        lines.extend(
            [
                f"### 条款 {index}",
                "",
                "原文摘录：",
                "",
                f"> {truncate_text(paragraph, 220)}",
                "",
                review_text,
                "",
                "参考片段：",
                "",
            ]
        )
        for reference in references:
            source = str(reference.metadata.get("source", "未知来源"))
            kind = str(reference.metadata.get("kind", "paragraph"))
            lines.append(f"- {kind} | {source} | {truncate_text(reference.page_content, 120)}")
        lines.append("")

    return "\n".join(lines)
