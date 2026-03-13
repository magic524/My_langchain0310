from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from langchain_core.documents import Document


MODULE_PATH = Path(__file__).with_name("contract_review_agent.py")
SPEC = importlib.util.spec_from_file_location("contract_review_agent", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ContractReviewAgentTests(unittest.TestCase):
    def test_sanitize_review_text_removes_thinking_and_keeps_structured_result(self) -> None:
        raw_text = (
            "Thinking Process:\n"
            "1. analyze\n"
            "<think>hidden reasoning</think>\n"
            "风险级别：中\n"
            "问题说明：存在歧义\n"
            "审查批注：请明确\n"
            "建议修改：补充定义\n"
            "参考依据：历史批注\n"
        )

        cleaned = MODULE.sanitize_review_text(raw_text)

        self.assertTrue(cleaned.startswith("风险级别：中"))
        self.assertNotIn("Thinking Process", cleaned)
        self.assertNotIn("<think>", cleaned)

    def test_sanitize_review_text_collapses_no_comment_output(self) -> None:
        raw_text = "Thinking Process: none\n无需批注\n参考片段：..."

        cleaned = MODULE.sanitize_review_text(raw_text)

        self.assertEqual(cleaned, "无需批注")

    def test_configure_runtime_env_supports_local_openai_compatible_llm(self) -> None:
        env = {
            "OPENAI_LLM_MODEL": "InstructModel",
            "OPENAI_MODEL_PROVIDER": "openai",
            "OPENAI_API_BASE": "http://10.130.61.231:8001/v1",
            "OPENAI_API_KEY": "E***Y",
            "OPENAI_TEMPERATURE": "0.7",
            "OPENAI_EXTRA_BODY": '{"top_k": 20, "chat_template_kwargs": {"enable_thinking": true}}',
        }

        with (
            mock.patch.object(MODULE, "find_dotenv", return_value=""),
            mock.patch.object(MODULE, "load_dotenv"),
            mock.patch.dict(MODULE.os.environ, env, clear=True),
        ):
            config = MODULE.configure_runtime_env()

        self.assertEqual(config.model_name, "InstructModel")
        self.assertEqual(config.model_provider, "openai")
        self.assertEqual(config.base_url, "http://10.130.61.231:8001/v1")
        self.assertEqual(config.api_key, "E***Y")
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(
            config.extra_body,
            {"top_k": 20, "chat_template_kwargs": {"enable_thinking": True}},
        )

    def test_parse_knowledge_base_skips_doc_when_extractor_is_unavailable(self) -> None:
        legacy_doc = Path("legacy.doc")
        modern_docx = Path("modern.docx")
        parsed_docx = MODULE.ParsedWordFile(
            path=modern_docx,
            file_type="docx",
            role="review",
            text="测试内容",
            paragraphs=["测试内容"],
            comments=[],
            revisions=[],
        )

        with (
            mock.patch.object(MODULE, "iter_word_files", return_value=[legacy_doc, modern_docx]),
            mock.patch.object(MODULE, "infer_file_role", return_value="review"),
            mock.patch.object(
                MODULE,
                "parse_word_file",
                side_effect=[
                    MODULE.DocExtractionUnavailableError("当前环境无法解析旧版 .doc 文件。"),
                    parsed_docx,
                ],
            ),
        ):
            result = MODULE.parse_knowledge_base(Path("knowledge"))

        self.assertEqual(result.parsed_files, [parsed_docx])
        self.assertEqual(result.skipped_files, [legacy_doc])

    def test_extract_doc_best_effort_uses_converted_docx_when_available(self) -> None:
        converted = MODULE.ParsedWordFile(
            path=Path("temp.docx"),
            file_type="docx",
            role="review",
            text="转换后的内容",
            paragraphs=["转换后的内容"],
            comments=["法务：批注"],
            revisions=["插入：补充条款"],
        )

        with mock.patch.object(MODULE, "_extract_doc_via_converted_docx", return_value=converted):
            parsed = MODULE.extract_doc_best_effort(Path("legacy.doc"), "review")

        self.assertEqual(parsed.file_type, "doc")
        self.assertEqual(parsed.path, Path("legacy.doc"))
        self.assertEqual(parsed.paragraphs, ["转换后的内容"])
        self.assertEqual(parsed.comments, ["法务：批注"])
        self.assertEqual(parsed.revisions, ["插入：补充条款"])

    def test_extract_doc_best_effort_raises_when_no_extractor_available(self) -> None:
        with (
            mock.patch.object(MODULE, "_extract_doc_via_converted_docx", return_value=None),
            mock.patch.object(MODULE.shutil, "which", return_value=None),
        ):
            with self.assertRaises(MODULE.DocExtractionUnavailableError):
                MODULE.extract_doc_best_effort(Path("legacy.doc"), "review")

    def test_extract_docx_reads_paragraphs_comments_and_revisions(self) -> None:
        document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>第一条 付款期限为30日。</w:t></w:r></w:p>
            <w:p>
              <w:ins><w:r><w:t>新增违约金条款。</w:t></w:r></w:ins>
              <w:del><w:r><w:delText>删除免责描述。</w:delText></w:r></w:del>
            </w:p>
          </w:body>
        </w:document>
        """
        comments_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:comment w:id="0" w:author="法务A">
            <w:p><w:r><w:t>建议明确付款节点。</w:t></w:r></w:p>
          </w:comment>
        </w:comments>
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            docx_path = Path(temp_dir) / "reviewed.docx"
            with zipfile.ZipFile(docx_path, "w") as archive:
                archive.writestr("word/document.xml", document_xml)
                archive.writestr("word/comments.xml", comments_xml)

            parsed = MODULE.extract_docx(docx_path, "review")

        self.assertEqual(parsed.file_type, "docx")
        self.assertIn("第一条 付款期限为30日。", parsed.paragraphs)
        self.assertEqual(parsed.comments, ["法务A：建议明确付款节点。"])
        self.assertIn("插入：新增违约金条款。", parsed.revisions)
        self.assertIn("删除：删除免责描述。", parsed.revisions)

    def test_retrieve_references_prioritizes_review_comments(self) -> None:
        docs = [
            Document(
                page_content="付款期限可明确为收到发票后三十日内支付。",
                metadata={"source": "原合同/a.docx", "role": "original", "kind": "paragraph"},
            ),
            Document(
                page_content="法务建议：付款节点必须与验收条件绑定，避免无条件付款。",
                metadata={"source": "审查/a_review.docx", "role": "review", "kind": "comment"},
            ),
        ]

        results = MODULE.retrieve_references("付款节点和验收条件需要明确", docs, top_k=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].metadata["role"], "review")
        self.assertEqual(results[0].metadata["kind"], "comment")

    def test_select_target_paragraphs_skips_short_duplicates(self) -> None:
        parsed = MODULE.ParsedWordFile(
            path=Path("demo.docx"),
            file_type="docx",
            role="original",
            text="",
            paragraphs=[
                "定义",
                "第二条 双方应在验收完成后十五个工作日内支付合同价款。",
                "第二条 双方应在验收完成后十五个工作日内支付合同价款。",
                "第三条 任一方不得擅自披露保密信息。",
            ],
            comments=[],
            revisions=[],
        )

        paragraphs = MODULE.select_target_paragraphs(parsed, max_paragraphs=10, min_chars=12)

        self.assertEqual(
            paragraphs,
            [
                "第二条 双方应在验收完成后十五个工作日内支付合同价款。",
                "第三条 任一方不得擅自披露保密信息。",
            ],
        )

    def test_normalize_path_for_current_os_keeps_windows_path_on_windows(self) -> None:
        with mock.patch.object(MODULE.os, "name", "nt"):
            path_value = MODULE.normalize_path_for_current_os(r"E:\contracts\input.docx")

        self.assertEqual(path_value, r"E:\contracts\input.docx")

    def test_normalize_path_for_current_os_converts_windows_path_on_posix(self) -> None:
        with mock.patch.object(MODULE.os, "name", "posix"):
            path_value = MODULE.normalize_path_for_current_os(r"E:\contracts\input.docx")

        self.assertEqual(path_value, "/mnt/e/contracts/input.docx")


if __name__ == "__main__":
    unittest.main()
