from __future__ import annotations

import json
from pathlib import Path

from Contract_Review_System.GUI.service import GuiPipelineService, GuiReviewRequest
from Contract_Review_System.only_prompt_local_llm.src.only_prompt_local_llm.local_model_runner import (
    build_review_messages,
)


def test_build_review_messages_for_party_a_with_extra_instruction() -> None:
    messages, prompt_context = build_review_messages(
        "合同全文示例",
        review_stance="party_a",
        extra_user_instruction="重点关注付款条款。",
    )

    assert prompt_context.review_stance == "party_a"
    assert prompt_context.extra_user_instruction == "重点关注付款条款。"
    assert messages[0][0] == "system"
    assert "甲方" in messages[1][1]
    assert "重点关注付款条款" in messages[1][1]


def test_build_review_messages_for_party_b_without_extra_instruction() -> None:
    messages, prompt_context = build_review_messages(
        "合同全文示例",
        review_stance="party_b",
    )

    assert prompt_context.review_stance == "party_b"
    assert prompt_context.extra_user_instruction == ""
    assert "乙方" in messages[1][1]
    assert "用户补充要求" not in messages[1][1]


def test_gui_pipeline_service_passes_review_preferences(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "demo.docx"
    input_path.write_text("placeholder", encoding="utf-8")

    received: dict[str, object] = {}

    monkeypatch.setattr(
        "Contract_Review_System.GUI.service.load_runtime_config",
        lambda _env_path: "runtime-object",
    )
    monkeypatch.setattr(
        "Contract_Review_System.GUI.service.resolve_runtime_env_path",
        lambda: Path("fake.env"),
    )

    def fake_run_contract_review_pipeline(**kwargs: object) -> dict[str, str]:
        received.update(kwargs)
        output_dir = Path(str(kwargs["pipeline_output_dir"]))
        output_dir.mkdir(parents=True, exist_ok=True)
        primary_comment_file = output_dir / "原合同批注版_local_llm" / "demo_本地模型批注版.docx"
        primary_comment_file.parent.mkdir(parents=True, exist_ok=True)
        primary_comment_file.write_text("placeholder", encoding="utf-8")
        summary_path = output_dir / "pipeline_summary.json"
        summary_path.write_text(json.dumps({"ok": True}, ensure_ascii=False), encoding="utf-8")
        log_path = output_dir / "pipeline.log"
        log_path.write_text("done", encoding="utf-8")
        return {
            "pipeline_output_dir": str(output_dir),
            "primary_comment_file": str(primary_comment_file),
            "comment_output_dir": str(primary_comment_file.parent),
            "summary_path": str(summary_path),
            "log_path": str(log_path),
        }

    monkeypatch.setattr(
        "Contract_Review_System.GUI.service.run_contract_review_pipeline",
        fake_run_contract_review_pipeline,
    )

    service = GuiPipelineService(
        output_root=tmp_path / "outputs",
        word2md_output_root=tmp_path / "word2md_outputs",
    )
    result = service.run(
        GuiReviewRequest(
            input_path=str(input_path),
            review_stance="party_b",
            extra_user_instruction="优先关注违约责任。",
        )
    )

    assert received["input_value"] == str(input_path.resolve())
    assert received["runtime"] == "runtime-object"
    assert received["review_stance"] == "party_b"
    assert received["extra_user_instruction"] == "优先关注违约责任。"
    assert Path(result.primary_comment_file).exists()
    assert Path(result.summary_path).exists()
