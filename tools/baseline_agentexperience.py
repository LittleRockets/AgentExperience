"""Deterministic A/B baseline for the AgentExperience v0.2 Harness protocol."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_experience import HarnessState, Outcome, RunOutcome, SelectionDecision, agent_experience
from agent_experience.schema import events_pb2, experience_pb2

STRATEGIES = ("inspect-output", "retry-same-input", "dependency-first")
EXPERIENCE_ID = "exp-dependency-first"
CONTRACT_ID = "strategy://dependency-first@1"


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    text: str
    target_strategy: str
    relevant: bool


@dataclass(frozen=True, slots=True)
class Trial:
    task_id: str
    relevant: bool
    success: bool
    attempts: int
    selected: bool
    adopted: bool
    abstained: bool
    latency_ms: float


def make_tasks(samples_per_cohort: int) -> tuple[Task, ...]:
    """Build balanced tasks whose oracle is deterministic and independently checkable."""

    relevant = tuple(
        Task(
            f"debug-{index}",
            f"debug dependency failure case {index}",
            "dependency-first",
            True,
        )
        for index in range(samples_per_cohort)
    )
    irrelevant = tuple(
        Task(f"format-{index}", f"format report case {index}", "inspect-output", False)
        for index in range(samples_per_cohort)
    )
    return relevant + irrelevant


def active_experience() -> experience_pb2.ExperienceDefinition:
    tool = experience_pb2.ToolContract(
        contract_id=CONTRACT_ID,
        name="dependency-first",
        idempotent=True,
        has_external_side_effects=False,
    )
    return experience_pb2.ExperienceDefinition(
        experience_id=EXPERIENCE_ID,
        revision_id="rev-1",
        generation=1,
        schema_version=1,
        content_hash=b"baseline-agentexperience-v0.2",
        experience_type=experience_pb2.TASK_STRATEGY,
        status=experience_pb2.ACTIVE,
        summary="debug dependency failure using dependency-first strategy",
        applicability=experience_pb2.Applicability(
            trigger_keywords=["debug", "dependency", "failure"], required_tools=[tool]
        ),
        strategy=experience_pb2.DAG(
            nodes=[experience_pb2.DAGNode(node_id="dependency-first", tool=tool)],
            output_node_ids=["dependency-first"],
        ),
        source_run_ids=["validated-source-1", "validated-source-2"],
    )


def _execute(task: Task, preferred: str | None, max_attempts: int = 2) -> tuple[bool, int]:
    order = list(STRATEGIES)
    if preferred is not None:
        order.remove(preferred)
        order.insert(0, preferred)
    attempted = order[:max_attempts]
    success = task.target_strategy in attempted
    attempts = attempted.index(task.target_strategy) + 1 if success else len(attempted)
    return success, attempts


def run_baseline(tasks: tuple[Task, ...]) -> tuple[Trial, ...]:
    trials = []
    for task in tasks:
        started = time.perf_counter_ns()
        success, attempts = _execute(task, None)
        trials.append(
            Trial(task.task_id, task.relevant, success, attempts, False, False, False,
                  (time.perf_counter_ns() - started) / 1_000_000)
        )
    return tuple(trials)


def run_protocol(
    tasks: tuple[Task, ...], repository_path: Path, *, seed_experience: bool
) -> tuple[tuple[Trial, ...], dict[str, int]]:
    runtime = agent_experience(repository_path)
    if seed_experience:
        runtime.repository.append_event(
            events_pb2.EXPERIENCE_ACTIVATED,
            run_id="",
            producer="baseline-agentexperience",
            payload=active_experience(),
        )
    trials = []
    for task in tasks:
        started = time.perf_counter_ns()
        run = runtime.start(task.text, task_id=task.task_id, harness="baseline-agentexperience")
        tools = frozenset({CONTRACT_ID}) if task.relevant else frozenset()
        selection = run.select(HarnessState(task=task.text, available_tools=tools))[0]
        selected = selection.decision is SelectionDecision.SELECTED
        adopted = selected and selection.experience_id == EXPERIENCE_ID
        preferred = "dependency-first" if adopted else None
        success, attempts = _execute(task, preferred)
        outcome = RunOutcome(
            Outcome.SUCCESS if success else Outcome.FAILURE,
            metrics={"attempts": float(attempts)},
        )
        if selected:
            run.feedback(
                outcome,
                experience_id=selection.experience_id,
                revision_id=selection.revision_id,
                accepted=adopted,
            )
        run.complete(outcome)
        trials.append(
            Trial(
                task.task_id,
                task.relevant,
                success,
                attempts,
                selected,
                adopted,
                selection.decision is SelectionDecision.ABSTAINED,
                (time.perf_counter_ns() - started) / 1_000_000,
            )
        )
    audit = {
        "events_verified": runtime.repository.verify(),
        "active_runs_after": runtime.active_run_count,
        "applied_events": sum(
            event.event_type == events_pb2.EXPERIENCE_APPLIED
            for event in runtime.repository.events()
        ),
    }
    runtime.close()
    return tuple(trials), audit


def summarize(trials: tuple[Trial, ...]) -> dict[str, float | int]:
    relevant = tuple(trial for trial in trials if trial.relevant)
    irrelevant = tuple(trial for trial in trials if not trial.relevant)
    count = len(trials)
    return {
        "tasks": count,
        "success_rate": sum(trial.success for trial in trials) / count,
        "relevant_success_rate": sum(trial.success for trial in relevant) / len(relevant),
        "irrelevant_success_rate": sum(trial.success for trial in irrelevant) / len(irrelevant),
        "mean_attempts": statistics.fmean(trial.attempts for trial in trials),
        "selection_rate": sum(trial.selected for trial in trials) / count,
        "adoption_rate": sum(trial.adopted for trial in trials) / count,
        "abstention_rate": sum(trial.abstained for trial in trials) / count,
        "median_latency_ms": statistics.median(trial.latency_ms for trial in trials),
    }


def benchmark(samples_per_cohort: int, root: Path) -> dict[str, Any]:
    tasks = make_tasks(samples_per_cohort)
    baseline = run_baseline(tasks)
    abstain, abstain_audit = run_protocol(tasks, root / "abstain", seed_experience=False)
    assisted, assisted_audit = run_protocol(tasks, root / "assisted", seed_experience=True)
    negative_transfer = sum(
        assisted_trial.success < baseline_trial.success
        or assisted_trial.attempts > baseline_trial.attempts
        for baseline_trial, assisted_trial in zip(baseline, assisted, strict=True)
    )
    abstain_parity = all(
        (left.success, left.attempts) == (right.success, right.attempts)
        for left, right in zip(baseline, abstain, strict=True)
    )
    results: dict[str, Any] = {
        "method": "deterministic synthetic functional baseline",
        "samples_per_cohort": samples_per_cohort,
        "arms": {
            "baseline": summarize(baseline),
            "instrumented_abstain": summarize(abstain),
            "experience_assisted": summarize(assisted),
        },
        "abstain_behavioral_parity": abstain_parity,
        "negative_transfer_count": negative_transfer,
        "audits": {"instrumented_abstain": abstain_audit, "experience_assisted": assisted_audit},
    }
    results["passed"] = bool(
        abstain_parity
        and negative_transfer == 0
        and summarize(assisted)["success_rate"] > summarize(baseline)["success_rate"]
        and summarize(assisted)["irrelevant_success_rate"]
        == summarize(baseline)["irrelevant_success_rate"]
        and abstain_audit["active_runs_after"] == assisted_audit["active_runs_after"] == 0
        and assisted_audit["applied_events"] == samples_per_cohort
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-per-cohort", type=int, default=50)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples_per_cohort <= 0:
        parser.error("--samples-per-cohort must be positive")
    with tempfile.TemporaryDirectory() as directory:
        results = benchmark(args.samples_per_cohort, Path(directory))
    rendered = json.dumps(results, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not results["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
