from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ThresholdConfig:
    """Threshold configuration for matching and scoring."""

    clause_match_threshold: float = 0.35
    direction_consistency_threshold: float = 0.35
    explanation_accuracy_threshold: float = 0.55
    suggestion_accuracy_threshold: float = 0.55


@dataclass(slots=True)
class EvalConfig:
    """Evaluation runtime configuration."""

    participants: list[str]
    thresholds: ThresholdConfig
    use_llm_judge: bool = False


DEFAULT_PARTICIPANTS = ["third_party", "final_applied", "agent"]


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_eval_config(config_path: Path | None = None) -> EvalConfig:
    """Load evaluation config from JSON file.

    Args:
        config_path: Optional json config path.

    Returns:
        Parsed evaluation config.
    """
    payload: dict[str, Any] = {}
    if config_path is not None and config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, dict):
            payload = loaded

    participants = payload.get("participants")
    if not isinstance(participants, list) or not participants:
        participants = list(DEFAULT_PARTICIPANTS)

    threshold_payload = payload.get("thresholds") or {}
    if not isinstance(threshold_payload, dict):
        threshold_payload = {}

    thresholds = ThresholdConfig(
        clause_match_threshold=_safe_float(
            threshold_payload.get("clause_match_threshold"),
            ThresholdConfig.clause_match_threshold,
        ),
        direction_consistency_threshold=_safe_float(
            threshold_payload.get("direction_consistency_threshold"),
            ThresholdConfig.direction_consistency_threshold,
        ),
        explanation_accuracy_threshold=_safe_float(
            threshold_payload.get("explanation_accuracy_threshold"),
            ThresholdConfig.explanation_accuracy_threshold,
        ),
        suggestion_accuracy_threshold=_safe_float(
            threshold_payload.get("suggestion_accuracy_threshold"),
            ThresholdConfig.suggestion_accuracy_threshold,
        ),
    )

    use_llm_judge = bool(payload.get("use_llm_judge", False))
    return EvalConfig(participants=participants, thresholds=thresholds, use_llm_judge=use_llm_judge)
