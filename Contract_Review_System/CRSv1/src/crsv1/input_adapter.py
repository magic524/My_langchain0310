from __future__ import annotations

import json
from pathlib import Path

from .runtime_types import ContractInputBundle


CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[5]
DEFAULT_WORD2MD_OUTPUT_ROOT = REPO_ROOT / "data" / "contract_review_outputs" / "word2md"


def resolve_optional_path(path_str: str) -> Path:
    """Resolve an optional path string from repo-relative or absolute form."""

    candidate = Path(path_str).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def resolve_run_root(run_id: str, *, explicit_run_root: Path | None = None) -> Path:
    """Resolve a word2md run root from either explicit directory or run id."""

    if explicit_run_root is not None:
        return explicit_run_root.resolve()
    return (DEFAULT_WORD2MD_OUTPUT_ROOT / run_id).resolve()


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"JSON root must be an object: {path}"
        raise ValueError(msg)
    return payload


def load_contract_bundles(run_id: str, *, run_root: Path | None = None) -> tuple[list[ContractInputBundle], list[str], Path]:
    """Load normalized contract bundles from one word2md run."""

    resolved_root = resolve_run_root(run_id, explicit_run_root=run_root)
    summary_path = resolved_root / "run_summary.json"
    summary = _read_json(summary_path)

    bundles: list[ContractInputBundle] = []
    warnings: list[str] = []
    for result in summary.get("results", []):
        if not isinstance(result, dict):
            continue
        if str(result.get("status", "")) != "ok":
            sample_id = str(result.get("sample_id", "")).strip()
            warnings.append(f"{sample_id}: word2md failed")
            continue
        contract_id = str(result.get("sample_id", "")).strip()
        output_md = Path(str(result.get("output_md", ""))).resolve()
        if not contract_id or not output_md.exists():
            warnings.append(f"{contract_id or '<empty>'}: missing output.md")
            continue
        meta_path = output_md.with_name("meta.json")
        meta = _read_json(meta_path) if meta_path.exists() else {}
        bundles.append(
            ContractInputBundle(
                contract_id=contract_id,
                source_files={
                    "original_md": str(output_md),
                    "meta_path": str(meta_path),
                    "original_doc": str(meta.get("source_path", "")),
                },
                markdown_text=output_md.read_text(encoding="utf-8"),
                meta=meta,
            )
        )
    return bundles, warnings, resolved_root
