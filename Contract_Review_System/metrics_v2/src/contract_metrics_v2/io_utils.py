from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    """读取 utf-8 文本。"""

    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """读取 json 对象。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"JSON 根节点必须是对象: {path}"
        raise ValueError(msg)
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """写入 json 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """写入文本文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def resolve_run_root(project_root: Path, run_id: str) -> Path:
    """定位 word2md 的输出目录。"""

    run_root = (
        project_root
        / "Contract_Review_System"
        / "v2"
        / "word2md"
        / "outputs_md"
        / run_id
    ).resolve()
    if not run_root.exists():
        msg = f"word2md 输出目录不存在: {run_root}"
        raise FileNotFoundError(msg)
    return run_root
