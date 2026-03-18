from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .baseline_parser import parse_participant_markdown, select_participant_markdown
from .clause_parser import extract_clause_units
from .io_utils import read_json, read_text, resolve_run_root, write_json
from .label_parser import parse_label_markdown
from .types import ContractDataset, DatasetPayload


def _contract_id_from_sample_id(sample_id: str) -> str:
    return sample_id.split("/")[0]


def _find_sample(sample_map: dict[str, Path], marker: str) -> Path | None:
    for sample_id, path in sample_map.items():
        if marker in sample_id:
            return path
    return None


def _meta_path(markdown_path: Path) -> Path:
    return markdown_path.parent / "meta.json"


def _safe_source_path(meta_path: Path) -> str:
    if not meta_path.exists():
        return ""
    try:
        payload = read_json(meta_path)
    except Exception:  # noqa: BLE001
        return ""
    return str(payload.get("source_path", ""))


def build_dataset(project_root: Path, run_id: str, output_path: Path) -> DatasetPayload:
    """基于 word2md 输出构建 v2 数据集。"""

    run_root = resolve_run_root(project_root, run_id)
    summary_path = run_root / "run_summary.json"
    summary = read_json(summary_path)

    by_contract: dict[str, dict[str, Path]] = {}
    warnings: list[str] = []
    for item in summary.get("results", []):
        if not isinstance(item, dict):
            continue
        sample_id = str(item.get("sample_id", ""))
        if not sample_id:
            continue
        if str(item.get("status", "")) != "ok":
            warnings.append(f"{sample_id}: 转换失败")
            continue
        output_md = str(item.get("output_md", "")).strip()
        if not output_md:
            warnings.append(f"{sample_id}: output.md 缺失")
            continue
        contract_id = _contract_id_from_sample_id(sample_id)
        by_contract.setdefault(contract_id, {})[sample_id] = Path(output_md).resolve()

    contracts: list[ContractDataset] = []
    for contract_id, sample_map in sorted(by_contract.items()):
        contract_dir = run_root / contract_id
        original_md = _find_sample(sample_map, "/1-原合同")
        adoption_md = _find_sample(sample_map, "/4-采纳情况说明")

        source_files: dict[str, str] = {
            "run_root": str(contract_dir.resolve()),
            "original_md": str(original_md) if original_md else "",
            "original_doc": _safe_source_path(_meta_path(original_md)) if original_md else "",
            "adoption_md": str(adoption_md) if adoption_md else "",
            "adoption_doc": _safe_source_path(_meta_path(adoption_md)) if adoption_md else "",
            "third_party_md": "",
            "third_party_doc": "",
            "final_applied_md": "",
            "final_applied_doc": "",
        }

        clauses = []
        full_contract_text = ""
        if original_md is not None:
            full_contract_text = read_text(original_md)
            clauses = extract_clause_units(contract_id, full_contract_text)
        else:
            warnings.append(f"{contract_id}: 原合同 markdown 缺失")

        labels = []
        if adoption_md is not None:
            labels = parse_label_markdown(contract_id, adoption_md, _meta_path(adoption_md))
        else:
            warnings.append(f"{contract_id}: 采纳情况说明 markdown 缺失")

        participants: dict[str, list[Any]] = {"third_party": [], "final_applied": []}
        for participant in ("third_party", "final_applied"):
            selected = select_participant_markdown(contract_dir, participant)
            if selected is None:
                warnings.append(f"{contract_id}: {participant} markdown 缺失")
                continue
            source_files[f"{participant}_md"] = str(selected)
            source_files[f"{participant}_doc"] = _safe_source_path(_meta_path(selected))
            participants[participant] = parse_participant_markdown(contract_id, participant, selected)
            if not participants[participant]:
                warnings.append(f"{contract_id}: {participant} 未解析到风险点")

        contracts.append(
            ContractDataset(
                contract_id=contract_id,
                source_files=source_files,
                full_contract_text=full_contract_text,
                clauses=clauses,
                labels=labels,
                participants=participants,
            )
        )

    payload = DatasetPayload(
        meta={
            "generated_at": datetime.now().isoformat(),
            "run_id": run_id,
            "run_root": str(run_root),
            "contracts": len(contracts),
        },
        warnings=warnings,
        contracts=contracts,
    )

    serialized = {
        "meta": payload.meta,
        "warnings": payload.warnings,
        "contracts": [asdict(contract) for contract in payload.contracts],
    }
    write_json(output_path, serialized)
    return payload
