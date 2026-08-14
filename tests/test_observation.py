from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_experience import PredicateEvaluator, RedactionPolicy, Repository, SQLiteProjection
from agent_experience.events.factory import unpack_payload
from agent_experience.observer import ToolRegistry, ToolSpec, capture
from agent_experience.schema import events_pb2

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_sync_tool_lifecycle_redaction_outcome_and_projection(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "repo"
            with Repository(path) as repository:
                registry = ToolRegistry()

                def search(query: str, *, api_key: str) -> dict[str, object]:
                    return {"query": query, "count": 2, "api_key": api_key}

                registry.register(
                    ToolSpec(
                        "local://search@1",
                        "search",
                        search,
                        version="1",
                        idempotent=True,
                        has_external_side_effects=False,
                    )
                )
                observed_search = registry.observed("local://search@1", repository)

                @capture(
                    repository,
                    evaluator=PredicateEvaluator(
                        lambda result: result["count"] == 2,
                        evaluator_id="count-check",
                    ),
                )
                def run() -> dict[str, object]:
                    return observed_search("agent experience", api_key="do-not-store")

                self.assertEqual(run()["count"], 2)
                events = list(repository.events())
                self.assertEqual(repository.verify(), 5)

                tool_start = next(
                    event for event in events if event.event_type == events_pb2.TOOL_CALL_STARTED
                )
                tool_end = next(
                    event for event in events if event.event_type == events_pb2.TOOL_CALL_COMPLETED
                )
                payload = unpack_payload(tool_start)
                self.assertEqual(payload["kwargs"]["api_key"], "[REDACTED]")
                self.assertEqual(tool_end.causation_id, tool_start.event_id)
                self.assertEqual(tool_start.run_id, events[0].run_id)

                with SQLiteProjection(repository) as projection:
                    self.assertEqual(projection.update(), 5)
                    self.assertEqual(projection.update(), 5)

            connection = sqlite3.connect(path / "index" / "read-model.sqlite")
            try:
                run_row = connection.execute("SELECT status FROM runs").fetchone()
                tool_row = connection.execute(
                    "SELECT status, contract_id FROM tool_calls"
                ).fetchone()
                outcome_row = connection.execute(
                    "SELECT outcome, evaluator_id FROM outcomes"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(run_row, ("completed",))
            self.assertEqual(tool_row, ("completed", "local://search@1"))
            self.assertEqual(outcome_row, ("success", "count-check"))

    def test_tool_failure_is_recorded_and_propagated(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:
                registry = ToolRegistry()

                def fail() -> None:
                    raise LookupError("missing")

                registry.register(ToolSpec("local://fail", "fail", fail))
                observed_fail = registry.observed("local://fail", repository)

                @capture(repository)
                def run() -> None:
                    observed_fail()

                with self.assertRaisesRegex(LookupError, "missing"):
                    run()
                types = [event.event_type for event in repository.events()]
            self.assertEqual(
                types,
                [
                    events_pb2.RUN_STARTED,
                    events_pb2.TOOL_CALL_STARTED,
                    events_pb2.TOOL_CALL_FAILED,
                    events_pb2.RUN_FAILED,
                ],
            )

    def test_async_tool_context_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:
                registry = ToolRegistry()

                async def add_one(value: int) -> int:
                    await asyncio.sleep(0)
                    return value + 1

                registry.register(ToolSpec("local://add-one", "add-one", add_one))
                observed = registry.observed("local://add-one", repository)

                @capture(repository)
                async def run() -> int:
                    return await observed(4)

                self.assertEqual(asyncio.run(run()), 5)
                self.assertEqual(repository.verify(), 4)

    def test_observed_tool_requires_capture_context(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:
                registry = ToolRegistry()
                registry.register(ToolSpec("local://tool", "tool", lambda: None))
                tool = registry.observed("local://tool", repository)
                with self.assertRaisesRegex(RuntimeError, "capture context"):
                    tool()

    def test_redaction_bounds_nested_values(self) -> None:
        policy = RedactionPolicy(max_string_length=4, max_collection_items=2, max_depth=2)
        value = policy.sanitize(
            {"token": "secret", "items": ["abcdef", "second", "third"], "raw": b"123"}
        )
        self.assertEqual(value["token"], "[REDACTED]")
        self.assertEqual(value["items"], ["[MAX_DEPTH]", "[MAX_DEPTH]", "[TRUNCATED:1]"])
        self.assertEqual(value["[TRUNCATED]"], 1)


if __name__ == "__main__":
    unittest.main()
