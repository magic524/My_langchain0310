#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
METRICS_ROOT = SCRIPT_DIR.parent
SRC_DIR = METRICS_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from contract_metrics.reporter import write_reports
from contract_metrics.types import (
    EvaluationPayload,
    ExplanationMetrics,
    IdentificationCounts,
    IdentificationMetrics,
    ParticipantPolicyResult,
    SuggestionMetrics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render markdown/csv/json reports from evaluation payload")
    parser.add_argument("--evaluation-json", required=True, help="Path to evaluation payload JSON")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output report directory. Default: same directory as evaluation json",
    )
    return parser.parse_args()


def _to_result(item: dict) -> ParticipantPolicyResult:
    identification = item.get("identification") or {}
    counts = identification.get("counts") or {}

    return ParticipantPolicyResult(
        participant=str(item.get("participant", "")),
        policy=str(item.get("policy", "")),
        identification=IdentificationMetrics(
            accuracy=float(identification.get("accuracy", 0.0)),
            miss_rate=float(identification.get("miss_rate", 0.0)),
            false_positive_rate=float(identification.get("false_positive_rate", 0.0)),
            counts=IdentificationCounts(
                tp=int(counts.get("tp", 0)),
                fp=int(counts.get("fp", 0)),
                tn=int(counts.get("tn", 0)),
                fn=int(counts.get("fn", 0)),
            ),
        ),
        explanation=ExplanationMetrics(
            direction_consistency=float((item.get("explanation") or {}).get("direction_consistency", 0.0)),
            accuracy=float((item.get("explanation") or {}).get("accuracy", 0.0)),
            completeness=float((item.get("explanation") or {}).get("completeness", 0.0)),
            sample_size=int((item.get("explanation") or {}).get("sample_size", 0)),
        ),
        suggestion=SuggestionMetrics(
            direction_consistency=float((item.get("suggestion") or {}).get("direction_consistency", 0.0)),
            content_accuracy=float((item.get("suggestion") or {}).get("content_accuracy", 0.0)),
            completeness=float((item.get("suggestion") or {}).get("completeness", 0.0)),
            sample_size=int((item.get("suggestion") or {}).get("sample_size", 0)),
        ),
    )


def main() -> None:
    args = parse_args()
    payload_path = Path(args.evaluation_json).expanduser().resolve()
    payload_raw = json.loads(payload_path.read_text(encoding="utf-8"))

    participant_results = [_to_result(item) for item in (payload_raw.get("participant_results") or [])]

    payload = EvaluationPayload(
        meta=payload_raw.get("meta") or {},
        participant_results=participant_results,
        contract_results=payload_raw.get("contract_results") or [],
        warnings=[str(item) for item in (payload_raw.get("warnings") or [])],
    )

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else payload_path.parent
    outputs = write_reports(output_dir, payload)

    print("Report artifacts:")
    for key, value in outputs.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
