"""Reproducible v0.3 deterministic-selector reference benchmark."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_experience import (
    AdaptiveSelector,
    ExpectedEffect,
    PolicyCost,
    PolicyObject,
    RiskLevel,
    SelectionContext,
    SelectionObservation,
    evaluate_selection,
)


def benchmark(samples: int = 100) -> dict[str, Any]:
    context = SelectionContext(
        task="debug a failing dependency test",
        task_type="debug",
        available_tools=frozenset({"shell"}),
        max_prompt_tokens=64,
        max_risk=RiskLevel.MEDIUM,
    )
    policies = (
        PolicyObject(
            "dependency-debug",
            "rev-1",
            "debug dependency failures by inspecting the dependency graph",
            task_types=("debug",),
            trigger_keywords=("debug", "dependency"),
            required_tools=frozenset({"shell"}),
            expected_effect=ExpectedEffect(0.8, 0.2, 0.1),
            cost=PolicyCost(24),
            risk=RiskLevel.LOW,
            confidence=0.9,
            evidence=("run-a", "run-b", "run-c"),
        ),
        PolicyObject(
            "unsafe-retry",
            "rev-1",
            "retry every operation without a bound",
            task_types=("debug",),
            trigger_keywords=("debug",),
            required_tools=frozenset({"shell"}),
            expected_effect=ExpectedEffect(1.0, 0.4, 0.0),
            risk=RiskLevel.HIGH,
            confidence=1.0,
        ),
    )
    selector = AdaptiveSelector()
    durations: list[float] = []
    hard_constraint_bypasses = 0
    deterministic_ids: set[tuple[str, ...]] = set()
    for _ in range(samples):
        started = time.perf_counter_ns()
        result = selector.select(policies, context)
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
        deterministic_ids.add(tuple(item.experience_id for item in result.selected))
        hard_constraint_bypasses += sum(
            item.experience_id == "unsafe-retry" for item in result.selected
        )
    observations = tuple(
        SelectionObservation(
            f"holdout-{index}",
            "holdout",
            f"source-{index}",
            index % 4 != 3,
            index % 4 != 3,
            0.9 if index % 4 != 3 else 0.0,
            1.0 if index % 4 != 3 else 0.0,
            0.0,
            task_fingerprint=f"task-{index}",
        )
        for index in range(40)
    )
    evaluation = evaluate_selection(observations)
    ordered = sorted(durations)
    return {
        "schema_version": "0.3",
        "dataset": "synthetic-reference-v1",
        "sample_count": samples,
        "latency_ms": {
            "median": statistics.median(ordered),
            "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
            "max": max(ordered),
        },
        "hard_constraint_bypasses": hard_constraint_bypasses,
        "deterministic_output_count": len(deterministic_ids),
        "evaluation": asdict(evaluation),
        "limitations": [
            "synthetic reference data; not a real-world effectiveness claim",
            "local process timing; not a cross-platform SLA",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("--samples must be positive")
    rendered = json.dumps(benchmark(args.samples), indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
