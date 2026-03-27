from __future__ import annotations

import json
from pathlib import Path

from contract_tests.manual_feedback_review import build_contract_audit, render_overall_summary


def _write_meta(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_contract_audit_classifies_tp_fp_fn_and_unreviewed(tmp_path: Path) -> None:
    contract_dir = tmp_path / "demo"
    contract_dir.mkdir()
    (contract_dir / "output.md").write_text("# demo\n", encoding="utf-8")
    _write_meta(
        contract_dir / "meta.json",
        {
            "comment_anchors": [
                {
                    "comment_id": "1",
                    "author": "local_llm",
                    "comment_text": "风险点：主体信息缺失 说明：主体字段为空 建议：补充主体信息",
                    "paragraph_index": 10,
                    "paragraph_excerpt": "甲方主体字段为空。",
                },
                {
                    "comment_id": "2",
                    "author": "reviewer",
                    "comment_text": "采纳。原因：判断合理。",
                    "paragraph_index": 10,
                    "paragraph_excerpt": "甲方主体字段为空。",
                },
                {
                    "comment_id": "3",
                    "author": "local_llm",
                    "comment_text": "风险点：违约责任过重 说明：赔偿范围过宽 建议：限制赔偿范围",
                    "paragraph_index": 20,
                    "paragraph_excerpt": "赔偿全部损失。",
                },
                {
                    "comment_id": "4",
                    "author": "reviewer",
                    "comment_text": "未采纳。原因：该条符合当前谈判立场。",
                    "paragraph_index": 20,
                    "paragraph_excerpt": "赔偿全部损失。",
                },
                {
                    "comment_id": "5",
                    "author": "reviewer",
                    "comment_text": "本地模型遗漏的风险点提示：保密期限约定过长。",
                    "paragraph_index": 30,
                    "paragraph_excerpt": "保密义务持续有效。",
                },
                {
                    "comment_id": "6",
                    "author": "local_llm",
                    "comment_text": "风险点：争议解决地不利 说明：诉讼地单方有利 建议：改为原告所在地",
                    "paragraph_index": 40,
                    "paragraph_excerpt": "提交甲方所在地法院。",
                },
            ]
        },
    )

    audit = build_contract_audit("demo", contract_dir / "output.md", contract_dir / "meta.json")

    assert audit.model_output_count == 3
    assert audit.reviewed_count == 3
    assert audit.tp == 1
    assert audit.fp == 1
    assert audit.fn == 1
    assert audit.unreviewed == 1


def test_render_overall_summary_contains_aggregates(tmp_path: Path) -> None:
    contract_dir = tmp_path / "demo"
    contract_dir.mkdir()
    (contract_dir / "output.md").write_text("# demo\n", encoding="utf-8")
    _write_meta(contract_dir / "meta.json", {"comment_anchors": []})
    audit = build_contract_audit("demo", contract_dir / "output.md", contract_dir / "meta.json")

    report = render_overall_summary([audit], "manual-demo")

    assert "# manual-demo 人工反馈总体汇总" in report
    assert "| 合同 | 模型输出数 | 已人工判定数 | TP | FP | FN | 未判定 |" in report
    assert "| demo | 0 | 0 | 0 | 0 | 0 | 0 |" in report
    assert "## 总结分析" in report
