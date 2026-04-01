from __future__ import annotations

import json
from pathlib import Path


def load_word2md_summary(summary_path: Path) -> dict:
    """Load one `word2md` run summary from disk."""

    return json.loads(summary_path.read_text(encoding="utf-8"))


def build_artifact_paths(summary_path: Path) -> dict[str, str]:
    """Extract the key artifact paths for the first processed file."""

    payload = load_word2md_summary(summary_path)
    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        return {
            "run_summary.json": str(summary_path),
        }

    first_result = results[0] if isinstance(results[0], dict) else {}
    output_md = str(first_result.get("output_md", "")).strip()
    sample_output_dir = Path(output_md).parent if output_md else summary_path.parent

    return {
        "run_summary.json": str(summary_path),
        "sample_output_dir": str(sample_output_dir),
        "output.md": output_md,
        "meta.json": str(sample_output_dir / "meta.json"),
    }
