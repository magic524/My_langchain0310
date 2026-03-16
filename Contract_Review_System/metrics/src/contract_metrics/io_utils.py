from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    """Read UTF-8 text from file.

    Args:
        path: Input path.

    Returns:
        Text content.
    """
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """Read JSON object from file.

    Args:
        path: JSON path.

    Returns:
        Parsed JSON object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"JSON root must be object: {path}"
        raise ValueError(msg)
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON object with utf-8 encoding.

    Args:
        path: Output path.
        payload: Data payload.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Write text file with utf-8 encoding.

    Args:
        path: Output path.
        text: Text content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def discover_md_run_root(project_root: Path, md_run_id: str) -> Path:
    """Resolve datatype_test markdown run directory.

    Args:
        project_root: Workspace root.
        md_run_id: Run id inside outputs_md.

    Returns:
        Absolute run directory path.
    """
    run_root = (
        project_root
        / "Contract_Review_System"
        / "datatype_test"
        / "outputs_md"
        / md_run_id
    ).resolve()
    if not run_root.exists():
        msg = f"Markdown run directory not found: {run_root}"
        raise FileNotFoundError(msg)
    return run_root
