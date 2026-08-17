"""Minimal framework-neutral Harness integration for the v0.2 protocol."""

from agent_experience import (
    HarnessState,
    Outcome,
    RunOutcome,
    RuntimeEvent,
    agent_experience,
)
from agent_experience.schema import events_pb2


def run_custom_loop(task: str) -> dict[str, object]:
    experience = agent_experience("./experience-data")
    with experience.start(task, harness="custom-loop") as run:
        run.observe(RuntimeEvent(events_pb2.NODE_STARTED, {"node_id": "plan"}))
        selection = run.select(HarnessState(task=task, framework="custom"))

        # The Harness owns planning and execution. Advice can be selected or safely abstain.
        result = {
            "task": task,
            "selection": selection[0].decision.value,
            "completed": True,
        }
        run.complete(RunOutcome(Outcome.SUCCESS, result=result))
    experience.close()
    return result


if __name__ == "__main__":
    print(run_custom_loop("inspect and repair the failing test"))
