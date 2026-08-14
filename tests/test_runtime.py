from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from agent_experience import agent_experience
from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_path_once_run_and_tool_are_automatic(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            @experience.tool
            def get_weather(city: str) -> dict[str, object]:
                return {"city": city, "temperature_c": 22, "fresh": True}

            @experience.run(verify=lambda result: bool(result["fresh"]))
            def agent(city: str) -> dict[str, object]:
                return get_weather(city)

            self.assertEqual(agent("Berlin")["temperature_c"], 22)
            experience.flush()
            events = list(experience.repository.events())
            types = [event.event_type for event in events]
            self.assertEqual(
                types[:5],
                [
                    events_pb2.RUN_STARTED,
                    events_pb2.TOOL_CALL_STARTED,
                    events_pb2.TOOL_CALL_COMPLETED,
                    events_pb2.RUN_COMPLETED,
                    events_pb2.OUTCOME_EVALUATED,
                ],
            )
            tool = next(
                event for event in events if event.event_type == events_pb2.TOOL_CALL_STARTED
            )
            payload = unpack_payload(tool)
            self.assertTrue(str(payload["contract_id"]).startswith("python://"))
            self.assertEqual(tool.run_id, events[0].run_id)
            self.assertIn(events_pb2.EXPERIENCE_CANDIDATE_CREATED, types)
            experience.close()

    def test_unverified_run_is_stored_but_cannot_create_candidate(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            @experience.run
            def agent() -> str:
                return "completed"

            self.assertEqual(agent(), "completed")
            experience.flush()
            types = [event.event_type for event in experience.repository.events()]
            self.assertEqual(types, [events_pb2.RUN_STARTED, events_pb2.RUN_COMPLETED])
            experience.close()

    def test_standalone_tool_gets_an_automatic_run(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            @experience.tool
            def get_weather(city: str) -> str:
                return city

            self.assertEqual(get_weather("Oslo"), "Oslo")
            types = [event.event_type for event in experience.repository.events()]
            self.assertEqual(
                types,
                [
                    events_pb2.RUN_STARTED,
                    events_pb2.TOOL_CALL_STARTED,
                    events_pb2.TOOL_CALL_COMPLETED,
                    events_pb2.RUN_COMPLETED,
                ],
            )
            experience.close()

    def test_async_nested_tool_and_failure_preserve_semantics(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            @experience.tool
            async def fail_tool() -> None:
                await asyncio.sleep(0)
                raise LookupError("missing")

            @experience.run
            async def agent() -> None:
                await fail_tool()

            with self.assertRaisesRegex(LookupError, "missing"):
                asyncio.run(agent())
            types = [event.event_type for event in experience.repository.events()]
            self.assertEqual(
                types,
                [
                    events_pb2.RUN_STARTED,
                    events_pb2.TOOL_CALL_STARTED,
                    events_pb2.TOOL_CALL_FAILED,
                    events_pb2.RUN_FAILED,
                ],
            )
            experience.close()

    def test_langgraph_gateway_uses_runtime_owned_storage(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            bridge = experience.langgraph(run_id="graph-run")

            bridge.consume(
                {
                    "type": "tasks",
                    "ns": (),
                    "data": {"id": "task-1", "name": "research", "input": {"q": "x"}},
                }
            )
            bridge.consume(
                {
                    "type": "tasks",
                    "ns": (),
                    "data": {"id": "task-1", "name": "research", "result": {"ok": True}},
                }
            )

            events = list(experience.repository.events())
            self.assertEqual(
                [event.event_type for event in events],
                [events_pb2.NODE_STARTED, events_pb2.NODE_COMPLETED],
            )
            self.assertEqual({event.run_id for event in events}, {"graph-run"})
            experience.close()


if __name__ == "__main__":
    unittest.main()
