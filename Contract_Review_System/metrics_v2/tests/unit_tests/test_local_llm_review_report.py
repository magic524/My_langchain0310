from __future__ import annotations

import json
from pathlib import Path

from contract_metrics_v2.local_llm_review_report import load_contract_audit, render_local_llm_review_report


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_render_local_llm_review_report_includes_formulae(tmp_path: Path) -> None:
    output_dir = tmp_path / "20260317_word2md_eval1-demo"
    output_dir.mkdir(parents=True)

    dataset_payload = {
        "meta": {},
        "warnings": [],
        "contracts": [
            {
                "contract_id": "demo-contract",
                "source_files": {
                    "original_doc": "demo.docx",
                    "original_md": "demo.md",
                    "adoption_md": "adoption.md",
                },
                "full_contract_text": "demo",
                "clauses": [
                    {
                        "clause_id": "demo_c001",
                        "contract_id": "demo-contract",
                        "section_title": "第一条",
                        "clause_title": "主体信息",
                        "clause_text": "甲方主体信息为空。",
                        "prev_clause_preview": "",
                        "next_clause_preview": "",
                        "context_text": "当前条款：甲方主体信息为空。",
                    }
                ],
                "labels": [],
                "participants": {},
            }
        ],
    }
    predictions_payload = [
        {
            "contract_id": "demo-contract",
            "risk_count": 1,
            "risks": [
                {
                    "risk_id": "demo_local_llm_001",
                    "contract_id": "demo-contract",
                    "title": "主体信息缺失",
                    "clause_text": "甲方主体信息为空。",
                    "explanation": "主体信息不完整会影响争议处理。",
                    "suggestion": "建议补充甲方统一社会信用代码和联系方式。",
                    "source_excerpt": "",
                    "status": "other",
                    "status_reason": "",
                    "clause_id": "demo_c001",
                    "match_score": 1.0,
                }
            ],
        }
    ]
    evaluation_payload = {
        "meta": {},
        "warnings": [],
        "participant_results": [
            {
                "participant": "local_llm",
                "policy": "adopted_only",
                "clause_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "risk_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "explanation_structure_score": 1.0,
                "suggestion_actionability_score": 1.0,
                "exact_title_overlap": 0.0,
                "exact_suggestion_overlap": 0.0,
                "matched_pairs": 1,
                "gold_risk_count": 1,
                "predicted_risk_count": 1,
            },
            {
                "participant": "local_llm",
                "policy": "all_labeled",
                "clause_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "risk_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "explanation_structure_score": 1.0,
                "suggestion_actionability_score": 1.0,
                "exact_title_overlap": 0.0,
                "exact_suggestion_overlap": 0.0,
                "matched_pairs": 1,
                "gold_risk_count": 1,
                "predicted_risk_count": 1,
            },
        ],
        "contract_results": [
            {
                "contract_id": "demo-contract",
                "participant": "local_llm",
                "policy": "adopted_only",
                "clause_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "risk_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "matched_pairs": [
                    {
                        "gold": {
                            "risk_id": "demo_label_001",
                            "contract_id": "demo-contract",
                            "title": "主体信息缺失",
                            "clause_text": "甲方主体信息为空。",
                            "explanation": "主体信息不完整会影响争议处理。",
                            "suggestion": "建议补充甲方统一社会信用代码和联系方式。",
                            "source_excerpt": "",
                            "status": "accept",
                            "status_reason": "已采纳",
                            "clause_id": "demo_c001",
                            "match_score": 1.0,
                        },
                        "prediction": {
                            "risk_id": "demo_local_llm_001",
                            "contract_id": "demo-contract",
                            "title": "主体信息缺失",
                            "clause_text": "甲方主体信息为空。",
                            "explanation": "主体信息不完整会影响争议处理。",
                            "suggestion": "建议补充甲方统一社会信用代码和联系方式。",
                            "source_excerpt": "",
                            "status": "other",
                            "status_reason": "",
                            "clause_id": "demo_c001",
                            "match_score": 1.0,
                        },
                        "score": 1.0,
                    }
                ],
                "unmatched_gold": [],
                "unmatched_prediction": [],
            },
            {
                "contract_id": "demo-contract",
                "participant": "local_llm",
                "policy": "all_labeled",
                "clause_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "risk_metrics": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                },
                "matched_pairs": [
                    {
                        "gold": {
                            "risk_id": "demo_label_001",
                            "contract_id": "demo-contract",
                            "title": "主体信息缺失",
                            "clause_text": "甲方主体信息为空。",
                            "explanation": "主体信息不完整会影响争议处理。",
                            "suggestion": "建议补充甲方统一社会信用代码和联系方式。",
                            "source_excerpt": "",
                            "status": "accept",
                            "status_reason": "已采纳",
                            "clause_id": "demo_c001",
                            "match_score": 1.0,
                        },
                        "prediction": {
                            "risk_id": "demo_local_llm_001",
                            "contract_id": "demo-contract",
                            "title": "主体信息缺失",
                            "clause_text": "甲方主体信息为空。",
                            "explanation": "主体信息不完整会影响争议处理。",
                            "suggestion": "建议补充甲方统一社会信用代码和联系方式。",
                            "source_excerpt": "",
                            "status": "other",
                            "status_reason": "",
                            "clause_id": "demo_c001",
                            "match_score": 1.0,
                        },
                        "score": 1.0,
                    }
                ],
                "unmatched_gold": [],
                "unmatched_prediction": [],
            },
        ],
    }

    _write_json(output_dir / "dataset_with_local_llm.json", dataset_payload)
    _write_json(output_dir / "local_llm_predictions.json", predictions_payload)
    _write_json(output_dir / "evaluation_result.json", evaluation_payload)

    audit = load_contract_audit(output_dir)
    report = render_local_llm_review_report([audit])

    assert "Precision = `1 / (1 + 0) = 100.00%`" in report
    assert "Clause TP/FP/FN" in report
    assert "demo-contract" in report
    assert "100.00%" in report
