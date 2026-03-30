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


def resolve_run_root(project_root: Path, run_id: str, explicit_run_root: Path | None = None) -> Path:
    """定位 word2md 的输出目录。

    优先读取新的统一输出目录 `data/contract_review_outputs/word2md/<run_id>`，
    同时兼容旧目录，便于平滑迁移历史跑批结果。
    """

    candidates: list[Path] = []
    if explicit_run_root is not None:
        candidates.append(explicit_run_root.resolve())
    candidates.extend(
        [
            (project_root / "data" / "contract_review_outputs" / "word2md" / run_id).resolve(),
            (project_root / "Contract_Review_System" / "word2md" / "outputs_md" / run_id).resolve(),
            (project_root / "Contract_Review_System" / "v2" / "word2md" / "outputs_md" / run_id).resolve(),
        ]
    )

    for run_root in candidates:
        if run_root.exists():
            return run_root

    candidate_text = "\n".join(f"- {path}" for path in candidates)
    msg = f"word2md 输出目录不存在，请检查以下候选路径:\n{candidate_text}"
    raise FileNotFoundError(msg)

