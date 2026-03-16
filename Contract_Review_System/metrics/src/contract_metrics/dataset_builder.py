from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .baseline_parser import parse_baseline_markdown, select_baseline_markdown
from .clause_parser import extract_clause_units
from .io_utils import discover_md_run_root, read_json, read_text, write_json
from .label_parser import parse_label_markdown
from .types import ContractDataset, DatasetPayload


def _contract_id_from_sample_id(sample_id: str) -> str:
    return sample_id.split("/")[0]


def _find_first_matching(sample_ids: list[str], marker: str) -> str | None:
    for sample_id in sample_ids:
        if marker in sample_id:
            return sample_id
    return None


def _output_meta_path(md_path: Path) -> Path:
    return md_path.parent / "meta.json"


def _safe_meta_source(meta_path: Path) -> str:
    if not meta_path.exists():
        return ""
    try:
        payload = read_json(meta_path)
    except Exception:  # noqa: BLE001
        return ""
    return str(payload.get("source_path", ""))


def build_dataset_from_md_run(
    *,
    project_root: Path,
    md_run_id: str,
    output_path: Path,
) -> DatasetPayload:
    """Build unified metrics dataset from datatype_test markdown run.

    Args:
        project_root: Workspace root.
        md_run_id: Markdown run id under outputs_md.
        output_path: Dataset output path.

    Returns:
        Built dataset payload.
    """
    run_root = discover_md_run_root(project_root, md_run_id)
    summary_path = run_root / "run_summary.json"
    summary = read_json(summary_path)

    warnings: list[str] = []
    results = summary.get("results") or []
    if not isinstance(results, list):
        msg = f"Invalid run summary format: {summary_path}"
        raise ValueError(msg)

    by_contract_samples: dict[str, dict[str, Path]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue

        sample_id = str(item.get("sample_id", ""))
        status = str(item.get("status", ""))
        if not sample_id:
            continue

        contract_id = _contract_id_from_sample_id(sample_id)
        by_contract_samples.setdefault(contract_id, {})

        if status != "ok":
            warnings.append(f"{sample_id}: conversion failed ({item.get('reason', 'unknown')})")
            continue

        output_md = item.get("output_md")
        if not output_md:
            warnings.append(f"{sample_id}: output.md path missing in run summary")
            continue

        by_contract_samples[contract_id][sample_id] = Path(str(output_md)).resolve()

    contracts: list[ContractDataset] = []
    for contract_id, sample_map in sorted(by_contract_samples.items()):
        sample_ids = sorted(sample_map.keys())

        original_sample = _find_first_matching(sample_ids, "/1-原合同")
        adoption_sample = _find_first_matching(sample_ids, "/4-采纳情况说明")

        contract_dir = (run_root / contract_id).resolve()

        source_files: dict[str, str] = {
            "run_root": str(contract_dir),
            "original_md": "",
            "original_doc": "",
            "third_party_md": "",
            "third_party_doc": "",
            "final_applied_md": "",
            "final_applied_doc": "",
            "adoption_md": "",
            "adoption_doc": "",
        }

        clauses = []
        if original_sample is not None:
            original_md_path = sample_map[original_sample]
            source_files["original_md"] = str(original_md_path)
            source_files["original_doc"] = _safe_meta_source(_output_meta_path(original_md_path))
            clauses = extract_clause_units(contract_id, read_text(original_md_path))
        else:
            warnings.append(f"{contract_id}: original contract markdown not found")

        labels = []
        if adoption_sample is not None:
            adoption_md_path = sample_map[adoption_sample]
            adoption_meta = _output_meta_path(adoption_md_path)
            source_files["adoption_md"] = str(adoption_md_path)
            source_files["adoption_doc"] = _safe_meta_source(adoption_meta)
            if adoption_meta.exists():
                labels = parse_label_markdown(
                    contract_id=contract_id,
                    adoption_md_path=adoption_md_path,
                    adoption_meta_path=adoption_meta,
                )
            else:
                warnings.append(f"{contract_id}: adoption meta.json missing ({adoption_meta})")
        else:
            warnings.append(f"{contract_id}: adoption markdown not found")

        baselines: dict[str, list[Any]] = {"third_party": [], "final_applied": []}
        for participant in ("third_party", "final_applied"):
            selected = select_baseline_markdown(contract_dir, participant)
            if selected is None:
                warnings.append(f"{contract_id}: {participant} markdown missing")
                continue

            source_files[f"{participant}_md"] = str(selected)
            source_files[f"{participant}_doc"] = _safe_meta_source(_output_meta_path(selected))
            baselines[participant] = parse_baseline_markdown(
                contract_id=contract_id,
                participant=participant,
                markdown_path=selected,
            )
            if not baselines[participant]:
                warnings.append(
                    f"{contract_id}: {participant} parsed 0 risk entries (possibly plain revised contract or missing comments)"
                )

        contracts.append(
            ContractDataset(
                contract_id=contract_id,
                source_files=source_files,
                clauses=clauses,
                labels=labels,
                baselines=baselines,
            )
        )

    payload = DatasetPayload(
        meta={
            "generated_at": datetime.now().isoformat(),
            "md_run_id": md_run_id,
            "run_root": str(run_root),
            "contracts": len(contracts),
        },
        contracts=contracts,
        warnings=warnings,
    )

    serialized = {
        "meta": payload.meta,
        "warnings": payload.warnings,
        "contracts": [asdict(contract) for contract in payload.contracts],
    }
    write_json(output_path, serialized)
    return payload
