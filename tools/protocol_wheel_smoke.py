"""Run v0.2 Protocol smoke checks against an installed wheel, outside the source package."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_experience import (
    PROTOCOL_API_VERSION,
    HarnessState,
    Outcome,
    RunOutcome,
    RuntimeEvent,
    agent_experience,
)
from agent_experience.schema import events_pb2


def main() -> None:
    results: dict[str, bool | str] = {"protocol_version": PROTOCOL_API_VERSION}
    with tempfile.TemporaryDirectory() as directory:
        experience = agent_experience(Path(directory) / "repository")

        custom = experience.start("custom task", harness="custom-loop")
        custom.select(HarnessState(task="custom task", framework="custom"))
        custom.complete(RunOutcome(Outcome.SUCCESS, result={"ok": True}))
        results["custom_loop"] = True

        graph = experience.start("graph task", harness="langgraph")
        bridge = experience.langgraph(run=graph)
        bridge.consume(
            {
                "type": "tasks",
                "ns": (),
                "data": {"id": "node-1", "name": "work", "input": {}},
            }
        )
        bridge.consume(
            {
                "type": "tasks",
                "ns": (),
                "data": {"id": "node-1", "name": "work", "result": {"ok": True}},
            }
        )
        graph.complete(RunOutcome(Outcome.SUCCESS))
        results["langgraph_loop"] = True

        coding = experience.start("repair test", harness="codex-like")
        succeeded = False
        for attempt in range(1, 3):
            coding.observe(
                RuntimeEvent(events_pb2.NODE_STARTED, {"node_id": "act", "attempt": attempt})
            )
            succeeded = attempt == 2
            coding.feedback(
                RunOutcome(
                    Outcome.SUCCESS if succeeded else Outcome.PARTIAL,
                    metrics={"attempt": float(attempt)},
                )
            )
            if succeeded:
                break
        coding.complete(RunOutcome(Outcome.SUCCESS if succeeded else Outcome.FAILURE))
        results["codex_like_loop"] = succeeded

        results["event_log_verified"] = experience.repository.verify() > 0
        results["no_active_runs"] = experience.active_run_count == 0
        experience.close()
    if not all(value is True for key, value in results.items() if key != "protocol_version"):
        raise SystemExit(json.dumps(results, sort_keys=True))
    print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
