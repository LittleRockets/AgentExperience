from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_experience import (
    ConformanceRequirements,
    HarnessState,
    Outcome,
    RunOutcome,
    run_protocol_conformance,
)
from agent_experience.adapters import (
    AdapterCapabilities,
    CapabilityLevel,
    LangGraphEventBridge,
    create_langchain_middleware,
    create_langgraph_callback,
)
from agent_experience.adapters.langchain import LANGCHAIN_CAPABILITIES, _tool_payload
from agent_experience.adapters.langgraph import LANGGRAPH_CAPABILITIES
from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2
from agent_experience.security import RedactionPolicy
from agent_experience.storage import Repository

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_capabilities_are_machine_readable(self) -> None:
        self.assertEqual(LANGCHAIN_CAPABILITIES.level, CapabilityLevel.ACTION)
        self.assertTrue(LANGCHAIN_CAPABILITIES.observes_models)
        self.assertFalse(LANGCHAIN_CAPABILITIES.supports_replay)
        self.assertEqual(LANGCHAIN_CAPABILITIES.protocol_version, "0.2")
        self.assertTrue(LANGCHAIN_CAPABILITIES.supports_async)

    def test_invalid_capability_dependencies_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "feedback support requires explicit"):
            AdapterCapabilities(
                framework="invalid",
                integration_version="1",
                level=CapabilityLevel.RUN,
                supports_feedback=True,
            )

    def test_langchain_tool_payload_uses_call_id_and_redacts(self) -> None:
        request = SimpleNamespace(
            tool_call={"id": "call-1", "name": "search", "args": {"token": "secret"}},
            tool=SimpleNamespace(name="search"),
        )
        payload = _tool_payload(request, RedactionPolicy())
        self.assertEqual(payload["tool_call_id"], "call-1")
        self.assertEqual(payload["args"]["token"], "[REDACTED]")

    def test_langgraph_tasks_routes_checkpoints_and_interrupts(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:
                bridge = LangGraphEventBridge(repository, run_id="graph-run")
                bridge.consume(
                    {
                        "type": "tasks",
                        "ns": ("subgraph",),
                        "data": {"id": "task-1", "name": "search", "input": {"q": "x"}},
                    }
                )
                bridge.consume(
                    {
                        "type": "tasks",
                        "ns": ("subgraph",),
                        "data": {
                            "id": "task-1",
                            "name": "search",
                            "result": {"found": True},
                            "interrupts": (),
                        },
                    }
                )
                bridge.consume({"type": "updates", "ns": (), "data": {"search": {"done": True}}})
                bridge.consume({"type": "checkpoints", "ns": (), "data": {"checkpoint_id": "cp-1"}})
                bridge.interrupt(
                    SimpleNamespace(
                        checkpoint_id="cp-1", checkpoint_ns=("subgraph",), interrupts=("review",)
                    )
                )
                bridge.resume(SimpleNamespace(checkpoint_id="cp-1", checkpoint_ns=("subgraph",)))
                events = list(repository.events())

            self.assertEqual(
                [event.event_type for event in events],
                [
                    events_pb2.NODE_STARTED,
                    events_pb2.NODE_COMPLETED,
                    events_pb2.ROUTE_SELECTED,
                    events_pb2.ARTIFACT_PRODUCED,
                    events_pb2.APPROVAL_REQUESTED,
                    events_pb2.APPROVAL_DECIDED,
                ],
            )
            self.assertEqual(events[1].causation_id, events[0].event_id)
            self.assertEqual(unpack_payload(events[2])["route"], "search")

    def test_langgraph_explicit_run_passes_behavioral_conformance(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            from agent_experience import agent_experience

            experience = agent_experience(Path(directory) / "repo")

            def exercise(runtime: object) -> str:
                self.assertIs(runtime, experience)
                run = experience.start("graph task", harness="langgraph")
                bridge = experience.langgraph(run=run)
                bridge.consume(
                    {
                        "type": "tasks",
                        "ns": (),
                        "data": {"id": "task-1", "name": "work", "input": {}},
                    }
                )
                bridge.consume(
                    {
                        "type": "tasks",
                        "ns": (),
                        "data": {"id": "task-1", "name": "work", "result": {"ok": True}},
                    }
                )
                run.select(HarnessState(task="graph task", framework="langgraph"))
                run.feedback(RunOutcome(Outcome.PARTIAL, metrics={"step": 1.0}))
                child = run.start_child("delegated graph task")
                child.complete(RunOutcome(Outcome.SUCCESS))
                run.complete(RunOutcome(Outcome.SUCCESS))
                return run.run_id

            report = run_protocol_conformance(
                experience,
                "langgraph-explicit",
                exercise,
                capabilities=LANGGRAPH_CAPABILITIES,
                requirements=ConformanceRequirements(
                    selection=True,
                    feedback=True,
                    delegation=True,
                    async_execution=True,
                ),
            )
            self.assertTrue(report.passed, report.checks)
            experience.close()

    def test_real_optional_adapter_classes_when_installed(self) -> None:
        try:
            from langchain.agents.middleware import AgentMiddleware
            from langgraph.callbacks import GraphCallbackHandler
        except ImportError:
            self.skipTest("LangChain/LangGraph optional dependencies are not installed")

        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:
                middleware = create_langchain_middleware(repository)
                callback = create_langgraph_callback(LangGraphEventBridge(repository))

        self.assertIsInstance(middleware, AgentMiddleware)
        self.assertIsInstance(callback, GraphCallbackHandler)
        self.assertNotEqual(type(callback).on_interrupt, GraphCallbackHandler.on_interrupt)
        self.assertNotEqual(type(callback).on_resume, GraphCallbackHandler.on_resume)


if __name__ == "__main__":
    unittest.main()
