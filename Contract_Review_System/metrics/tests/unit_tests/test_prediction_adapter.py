from __future__ import annotations

import json

from contract_metrics.prediction_adapter import load_agent_predictions_from_json


def test_load_agent_predictions_from_json(tmp_path) -> None:
    data = {
        "contracts": [
            {
                "contract_id": "demo_contract",
                "risks": [
                    {
                        "title": "主体信息不完整",
                        "clause_text": "统一社会信用代码/身份证号：",
                        "explanation": "主体信息不完整会影响送达。",
                        "suggestion": "补充统一社会信用代码。",
                        "has_risk": True,
                    }
                ],
            }
        ]
    }

    path = tmp_path / "pred.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    blocks = load_agent_predictions_from_json(json_path=path, contract_ids=["demo_contract"])
    assert len(blocks) == 1
    assert blocks[0].contract_id == "demo_contract"
    assert len(blocks[0].risks) == 1
    assert blocks[0].risks[0].title == "主体信息不完整"
