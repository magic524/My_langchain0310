from __future__ import annotations

import json
from pathlib import Path

from Contract_Review_System.common.local_llm_client import RuntimeConfig
from Contract_Review_System.contract_review_pipeline.src.contract_review_pipeline.pipeline import (
    run_contract_review_pipeline,
)
from Contract_Review_System.only_prompt_local_llm.src.only_prompt_local_llm.local_model_runner import (
    run_local_review_on_dataset,
)
from Contract_Review_System.only_prompt_local_llm.src.only_prompt_local_llm.review_types import RiskItem


def test_run_local_review_on_dataset_writes_pure_result(monkeypatch, tmp_path: Path) -> None:
    runtime = RuntimeConfig(
        model_name="demo",
        api_key="EMPTY",
        base_url="http://localhost:8000/v1",
        temperature=0.0,
        extra_body=None,
    )
    dataset_payload = {
        "contracts": [
            {
                "contract_id": "demo-contract",
                "source_files": {
                    "original_doc": "demo.docx",
                    "original_md": "demo/output.md",
                },
                "full_contract_text": "# demo contract",
            }
        ]
    }

    monkeypatch.setattr(
        "Contract_Review_System.only_prompt_local_llm.src.only_prompt_local_llm.local_model_runner.run_local_review_on_markdown",
        lambda contract_id, contract_text, runtime, **kwargs: (
            [
                RiskItem(
                    risk_id=f"{contract_id}_001",
                    contract_id=contract_id,
                    title="主体信息缺失",
                    clause_text="甲方主体信息为空。",
                    explanation="主体信息不完整会影响责任追究。",
                    suggestion="建议补充统一社会信用代码。",
                    source_excerpt=contract_text[:20],
                )
            ],
            '{"risks": []}',
        ),
    )

    result = run_local_review_on_dataset(
        runtime,
        dataset_payload,
        output_dir=tmp_path,
        run_id="demo-run",
    )

    result_payload = json.loads(Path(result["result_path"]).read_text(encoding="utf-8"))
    assert result_payload["meta"]["run_id"] == "demo-run"
    assert result_payload["contracts"][0]["contract_id"] == "demo-contract"
    assert "local_llm_risks" in result_payload["contracts"][0]
    assert "participants" not in result_payload["contracts"][0]


def test_run_contract_review_pipeline_generates_result(monkeypatch, tmp_path: Path) -> None:
    runtime = RuntimeConfig(
        model_name="demo",
        api_key="EMPTY",
        base_url="http://localhost:8000/v1",
        temperature=0.0,
        extra_body=None,
    )
    input_path = tmp_path / "demo.docx"
    input_path.write_text("placeholder", encoding="utf-8")

    word2md_output_root = tmp_path / "word2md_outputs"
    pipeline_output_dir = tmp_path / "pipeline_output"

    def fake_run_batch(
        items: list[object],
        run_id: str,
        output_root: Path,
        device: str,
        no_postprocess: bool,
        history_output_roots: list[Path],
    ) -> tuple[list[dict[str, str]], Path]:
        contract_dir = output_root / run_id / "demo-contract"
        contract_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = contract_dir / "output.md"
        meta_path = contract_dir / "meta.json"
        markdown_path.write_text("# 合同全文\n\n第一条 主体信息", encoding="utf-8")
        meta_path.write_text(
            json.dumps({"source_path": str(input_path)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary_path = output_root / run_id / "run_summary.json"
        summary_path.write_text(json.dumps({"run_id": run_id}, ensure_ascii=False), encoding="utf-8")
        return (
            [
                {
                    "sample_id": "demo-contract",
                    "status": "ok",
                    "output_md": str(markdown_path),
                }
            ],
            summary_path,
        )

    monkeypatch.setattr(
        "Contract_Review_System.contract_review_pipeline.src.contract_review_pipeline.pipeline.run_batch",
        fake_run_batch,
    )
    monkeypatch.setattr(
        "Contract_Review_System.contract_review_pipeline.src.contract_review_pipeline.pipeline.run_local_review_on_markdown",
        lambda contract_id, contract_text, runtime, **kwargs: (
            [
                RiskItem(
                    risk_id=f"{contract_id}_001",
                    contract_id=contract_id,
                    title="主体信息缺失",
                    clause_text="甲方主体信息为空。",
                    explanation="主体信息不完整会影响责任追究。",
                    suggestion="建议补充统一社会信用代码。",
                    source_excerpt=contract_text[:20],
                )
            ],
            '{"risks": []}',
        ),
    )
    monkeypatch.setattr(
        "Contract_Review_System.contract_review_pipeline.src.contract_review_pipeline.pipeline.export_local_llm_comment_docs",
        lambda result_path, output_dir: output_dir.mkdir(parents=True, exist_ok=True) or {"contracts": []},
    )

    result = run_contract_review_pipeline(
        input_value=str(input_path),
        run_name="demo-run",
        runtime=runtime,
        pipeline_output_dir=pipeline_output_dir,
        word2md_output_root=word2md_output_root,
    )

    result_payload = json.loads(Path(result["local_llm_result_path"]).read_text(encoding="utf-8"))
    assert result_payload["meta"]["run_name"] == "demo-run"
    assert result_payload["contracts"][0]["source_files"]["original_doc"] == str(input_path)
    assert Path(result["comment_output_dir"]).exists()
    assert Path(result["log_path"]).exists()
