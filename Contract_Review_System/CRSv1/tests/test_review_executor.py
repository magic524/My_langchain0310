from __future__ import annotations

from Contract_Review_System.CRSv1.src.crsv1.review_executor import _extract_json_payload


def test_extract_json_payload_prefers_top_level_risks() -> None:
    raw_text = """
{
  "risks": [
    {
      "target_clause_id": "n1",
      "target_text": "甲方：",
      "risk_title": "甲方主体信息缺失",
      "risk_level": "medium",
      "risk_type": "其他",
      "explanation": "甲方信息不完整。",
      "suggestion": "补齐主体信息。",
      "evidence_source": "前言"
    },
    {
      "target_clause_id": "n2",
      "target_text": "服务费_____元",
      "risk_title": "服务费用金额空白",
      "risk_level": "high",
      "risk_type": "付款",
      "explanation": "付款金额未填写。",
      "suggestion": "补充明确金额。",
      "evidence_source": "付款条款"
    }
  ]
}
""".strip()

    payload = _extract_json_payload(raw_text)

    assert "risks" in payload
    assert len(payload["risks"]) == 2
    assert payload["risks"][0]["risk_title"] == "甲方主体信息缺失"


def test_extract_json_payload_salvages_risk_items_from_malformed_outer_json() -> None:
    raw_text = """
{
  "risks": [
    {
      "target_clause_id": "n1",
      "target_text": "甲方：",
      "risk_title": "甲方主体信息缺失",
      "risk_level": "medium",
      "risk_type": "其他",
      "explanation": "甲方信息不完整。",
      "suggestion": "补齐主体信息。",
      "evidence_source": "前言"
    },
    {
      "target_clause_id": "n2",
      "target_text": "服务费\"_____\"元",
      "risk_title": "服务费用金额空白",
      "risk_level": "high",
      "risk_type": "付款",
      "explanation": "付款金额未填写。",
      "suggestion": "补充明确金额。",
      "evidence_source": "付款条款"
    }
  ]
""".strip()

    payload = _extract_json_payload(raw_text)

    assert "risks" in payload
    assert len(payload["risks"]) >= 1
    assert payload["risks"][0]["risk_title"] == "甲方主体信息缺失"
