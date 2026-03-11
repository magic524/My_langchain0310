from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from langchain_core.documents import Document


MODULE_PATH = Path(__file__).with_name("contract_review_agent.py")
SPEC = importlib.util.spec_from_file_location("contract_review_agent", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ContractReviewAgentTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
