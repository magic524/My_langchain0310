from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
ONLY_PROMPT_SRC = PROJECT_ROOT / "Contract_Review_System" / "only_prompt_local_llm" / "src"
if str(ONLY_PROMPT_SRC) not in sys.path:
    sys.path.insert(0, str(ONLY_PROMPT_SRC))

from only_prompt_local_llm.review_report import export_review_reports, render_contract_review_report


def test_render_contract_review_report_contains_risk_table() -> None:
    contract = {
        "contract_id": "demo-contract",
        "source_files": {
            "original_doc": "demo.docx",
            "original_md": "demo.md",
        },
        "participants": {
            "local_llm": [
                {
                    "title": "争议解决不利",
                    "clause_text": "争议提交甲方所在地法院处理。",
                    "explanation": "诉讼地对乙方不利，维权成本更高。",
                    "suggestion": "改为合同签订地或被告所在地法院管辖。",
                }
            ]
        },
    }

    report = render_contract_review_report(contract)

    assert "# demo-contract 审查报告" in report
    assert "## 风险点表格" in report
    assert "| 1 |" in report
    assert "demo.docx" in report


def test_export_review_reports_writes_contract_and_summary_files(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset_with_local_llm.json"
    dataset_path.write_text(
        json.dumps(
            {
                "contracts": [
                    {
                        "contract_id": "demo-contract",
                        "source_files": {
                            "original_doc": "demo.docx",
                            "original_md": "demo.md",
                        },
                        "participants": {
                            "local_llm": [
                                {
                                    "title": "付款条件模糊",
                                    "clause_text": "付款时间另行协商。",
                                    "explanation": "付款时间不明确，存在回款风险。",
                                    "suggestion": "明确付款节点和逾期责任。",
                                }
                            ]
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = export_review_reports(dataset_path, tmp_path / "reports")

    report_path = tmp_path / "reports" / "demo-contract_审查报告.md"
    summary_path = tmp_path / "reports" / "审查报告汇总.md"

    assert report_path.exists()
    assert summary_path.exists()
    assert summary["summary_path"] == str(summary_path)
    assert "demo-contract" in report_path.read_text(encoding="utf-8")
