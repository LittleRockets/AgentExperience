"""Reproducible local effectiveness benchmark for the v0.2 Experience Protocol."""

from __future__ import annotations

import concurrent.futures
import json
import statistics
import tempfile
import time
from pathlib import Path

from agent_experience import HarnessState, Outcome, RunOutcome, agent_experience

SAMPLES = 100
CONCURRENT_RUNS = 100


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def main() -> None:
    baseline: list[float] = []
    for _ in range(SAMPLES):
        started = time.perf_counter_ns()
        _ = {"ok": True}
        baseline.append((time.perf_counter_ns() - started) / 1_000_000)

    with tempfile.TemporaryDirectory() as directory:
        experience = agent_experience(Path(directory) / "repository")
        protocol: list[float] = []
        abstained = 0
        for index in range(SAMPLES):
            started = time.perf_counter_ns()
            run = experience.start(f"effect-{index}", harness="effect-benchmark")
            selection = run.select(HarnessState(task=f"effect-{index}"))
            abstained += int(selection[0].decision.value == "abstained")
            run.complete(RunOutcome(Outcome.SUCCESS, result={"ok": True}))
            protocol.append((time.perf_counter_ns() - started) / 1_000_000)

        def concurrent_run(index: int) -> str:
            run = experience.start(f"concurrent-{index}")
            run.complete(RunOutcome(Outcome.SUCCESS))
            return run.run_id

        concurrent_started = time.perf_counter_ns()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            run_ids = list(executor.map(concurrent_run, range(CONCURRENT_RUNS)))
        concurrent_ms = (time.perf_counter_ns() - concurrent_started) / 1_000_000

        events_verified = experience.repository.verify()
        automatic_applications = sum(
            1
            for event in experience.repository.events()
            if event.attributes.get("protocol_operation") == "apply"
        )
        results = {
            "samples": SAMPLES,
            "baseline_median_ms": statistics.median(baseline),
            "protocol_median_ms": statistics.median(protocol),
            "protocol_p95_ms": _percentile(protocol, 0.95),
            "protocol_max_ms": max(protocol),
            "abstention_rate": abstained / SAMPLES,
            "automatic_applications": automatic_applications,
            "concurrent_runs": CONCURRENT_RUNS,
            "concurrent_total_ms": concurrent_ms,
            "concurrent_unique_run_ids": len(set(run_ids)),
            "active_runs_after_test": experience.active_run_count,
            "events_verified": events_verified,
        }
        experience.close()

    passed = (
        results["abstention_rate"] == 1.0
        and results["automatic_applications"] == 0
        and results["concurrent_unique_run_ids"] == CONCURRENT_RUNS
        and results["active_runs_after_test"] == 0
        and results["protocol_p95_ms"] < 25.0
    )
    results["passed"] = passed
    print(json.dumps(results, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
