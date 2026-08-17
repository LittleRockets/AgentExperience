"""Deterministic Codex-like Observe -> Plan -> Act -> Verify -> Retry reference Harness."""

from collections.abc import Callable

from agent_experience import (
    HarnessState,
    Outcome,
    RunOutcome,
    RuntimeEvent,
    agent_experience,
)
from agent_experience.schema import events_pb2


def run_codex_like_loop(
    task: str,
    act: Callable[[int], object],
    verify: Callable[[object], bool],
    *,
    max_attempts: int = 3,
) -> object:
    """Run a bounded reference Loop; AgentExperience observes but never owns control flow."""

    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    experience = agent_experience("./experience-data")
    with experience.start(task, harness="codex-like-reference") as run:
        run.observe(RuntimeEvent(events_pb2.NODE_STARTED, {"node_id": "observe"}))
        run.select(
            HarnessState(
                task=task,
                framework="codex-like",
                harness_policy={"max_attempts": max_attempts},
            )
        )
        for attempt in range(1, max_attempts + 1):
            run.observe(
                RuntimeEvent(
                    events_pb2.NODE_STARTED,
                    {"node_id": "act", "attempt": attempt},
                )
            )
            result = act(attempt)
            passed = verify(result)
            run.feedback(
                RunOutcome(
                    Outcome.SUCCESS if passed else Outcome.PARTIAL,
                    result=result,
                    metrics={"attempt": float(attempt)},
                )
            )
            if passed:
                run.complete(RunOutcome(Outcome.SUCCESS, result=result))
                experience.close()
                return result
        run.complete(RunOutcome(Outcome.FAILURE, result=result))
    experience.close()
    return result


if __name__ == "__main__":
    print(run_codex_like_loop("repair a test", lambda attempt: attempt, lambda value: value >= 2))
