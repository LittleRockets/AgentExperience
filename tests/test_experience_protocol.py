from __future__ import annotations

import asyncio
import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path

from agent_experience import (
    ConformanceReasonCode,
    ConformanceRequirements,
    ConformanceStatus,
    DeterministicMiner,
    Evaluation,
    HarnessState,
    Outcome,
    RunFeatures,
    RunOutcome,
    RunState,
    RuntimeEvent,
    SelectionDecision,
    SQLiteProjection,
    agent_experience,
    build_baseline_profile,
    definition_from_delta,
    run_protocol_conformance,
)
from agent_experience.adapters import AdapterCapabilities, CapabilityLevel
from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2, experience_pb2

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class ExperienceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_explicit_run_observe_select_feedback_complete(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            run = experience.start(
                "debug a failing test",
                agent="test-agent",
                harness="custom-loop",
                task_id="task-1",
                model_id="test-model",
                metadata={"token": "must-not-leak"},
            )

            evidence_id = run.observe(
                RuntimeEvent(
                    events_pb2.NODE_STARTED,
                    {"node_id": "inspect", "observation": "test failed"},
                )
            )
            selection = run.select(HarnessState(task="debug a failing test"))
            self.assertEqual(selection[0].decision, SelectionDecision.ABSTAINED)
            run.feedback(
                RunOutcome(Outcome.UNKNOWN, metrics={"attempt": 1.0}),
                accepted=False,
            )
            run.complete(
                RunOutcome(
                    Outcome.SUCCESS,
                    result={"fixed": True},
                    tokens=17,
                    latency_ms=12.5,
                    tool_cost=0.01,
                    risk="low",
                ),
                evaluation=Evaluation(Outcome.SUCCESS, 1.0, "tests", "1", (evidence_id,)),
            )

            self.assertEqual(run.state, RunState.COMPLETED)
            events = list(experience.repository.events())
            self.assertEqual(
                [event.event_type for event in events],
                [
                    events_pb2.RUN_STARTED,
                    events_pb2.NODE_STARTED,
                    events_pb2.EXPERIENCE_ADVISED,
                    events_pb2.OUTCOME_EVALUATED,
                    events_pb2.RUN_COMPLETED,
                    events_pb2.OUTCOME_EVALUATED,
                ],
            )
            self.assertEqual(events[1].run_id, run.run_id)
            self.assertEqual(unpack_payload(events[0])["metadata"]["token"], "[REDACTED]")
            terminal = unpack_payload(events[-2])
            self.assertEqual(terminal["outcome"], "success")
            self.assertEqual(terminal["tokens"], 17.0)
            with self.assertRaisesRegex(RuntimeError, "completed experience run"):
                run.observe(RuntimeEvent(events_pb2.NODE_COMPLETED, {}))
            experience.close()

    def test_cancel_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            run = experience.start("cancel me")
            run.cancel("caller cancelled")
            self.assertEqual(run.state, RunState.CANCELLED)
            self.assertEqual(
                [event.event_type for event in experience.repository.events()],
                [events_pb2.RUN_STARTED, events_pb2.RUN_CANCELLED],
            )
            with self.assertRaisesRegex(RuntimeError, "cancelled experience run"):
                run.complete(RunOutcome(Outcome.UNKNOWN))
            experience.close()

    def test_concurrent_runs_keep_identity_isolated(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            def execute(index: int) -> str:
                run = experience.start(f"task-{index}", task_id=f"task-{index}")
                run.observe(RuntimeEvent(events_pb2.NODE_STARTED, {"index": index}))
                run.complete(RunOutcome(Outcome.SUCCESS, result=index))
                return run.run_id

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                run_ids = list(executor.map(execute, range(32)))

            self.assertEqual(len(set(run_ids)), 32)
            events = list(experience.repository.events())
            self.assertEqual(len(events), 96)
            by_run: dict[str, list[int]] = {}
            for event in events:
                by_run.setdefault(event.run_id, []).append(event.event_type)
            self.assertEqual(set(by_run), set(run_ids))
            self.assertTrue(
                all(
                    types
                    == [events_pb2.RUN_STARTED, events_pb2.NODE_STARTED, events_pb2.RUN_COMPLETED]
                    for types in by_run.values()
                )
            )
            experience.close()

    def test_contract_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "task must not be empty"):
            HarnessState(task="")
        with self.assertRaisesRegex(ValueError, "event_type must be specified"):
            RuntimeEvent(events_pb2.EVENT_TYPE_UNSPECIFIED)
        with self.assertRaisesRegex(ValueError, "cost metrics"):
            RunOutcome(Outcome.UNKNOWN, tokens=-1)

    def test_active_prompt_delta_is_budgeted_advice_and_requires_harness_adoption(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            mining = DeterministicMiner().mine(
                build_baseline_profile("travel", "1"),
                (
                    RunFeatures("source-a", frozenset({"budget", "transport"})),
                    RunFeatures("source-b", frozenset({"budget", "transport"})),
                ),
            )
            definition = definition_from_delta(mining, task_type="travel_plan")
            definition.status = experience_pb2.ACTIVE
            experience.repository.append_event(
                events_pb2.EXPERIENCE_ACTIVATED,
                run_id="",
                producer="test",
                payload=definition,
            )
            run = experience.start("plan New York")
            selected = run.select(
                HarnessState(
                    task="plan New York travel",
                    harness_policy={"task_type": "travel_plan"},
                    budget={
                        "max_context_tokens": 8192,
                        "base_input_tokens": 100,
                        "reserved_output_tokens": 1000,
                        "max_experience_tokens": 64,
                    },
                )
            )[0]
            self.assertEqual(selected.decision, SelectionDecision.SELECTED)
            self.assertIn("V0_2_POLICY_DELTA_ADVICE", selected.reason_codes)
            self.assertIn("HARNESS_ADOPTION_REQUIRED", selected.reason_codes)
            self.assertTrue(any("output.constraints.budget" in step for step in selected.steps))
            self.assertGreater(selected.cost, 0)
            self.assertFalse(
                any(
                    event.event_type == events_pb2.EXPERIENCE_APPLIED
                    for event in experience.repository.events()
                )
            )
            run.feedback(
                RunOutcome(Outcome.SUCCESS),
                experience_id=selected.experience_id,
                revision_id=selected.revision_id,
                accepted=True,
            )
            run.complete(RunOutcome(Outcome.SUCCESS))
            self.assertTrue(
                any(
                    event.event_type == events_pb2.EXPERIENCE_APPLIED
                    for event in experience.repository.events()
                )
            )
            experience.close()

    def test_prompt_delta_fails_closed_without_explicit_budget(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            mining = DeterministicMiner().mine(
                build_baseline_profile("travel", "1"),
                (
                    RunFeatures("source-a", frozenset({"budget"})),
                    RunFeatures("source-b", frozenset({"budget"})),
                ),
            )
            definition = definition_from_delta(mining, task_type="travel_plan")
            definition.status = experience_pb2.ACTIVE
            experience.repository.append_event(
                events_pb2.EXPERIENCE_ACTIVATED,
                run_id="",
                producer="test",
                payload=definition,
            )
            run = experience.start("plan New York")
            rejected = run.select(
                HarnessState(
                    task="plan New York travel",
                    harness_policy={"task_type": "travel_plan"},
                )
            )[0]
            self.assertEqual(rejected.decision, SelectionDecision.REJECTED)
            self.assertEqual(rejected.reason_codes, ("MISSING_TOKEN_BUDGET",))
            run.cancel("test complete")
            experience.close()

    def test_unknown_event_is_fail_closed_unless_explicitly_optional(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            run = experience.start("compatibility")
            with self.assertRaisesRegex(ValueError, "unknown critical event type 1001"):
                run.observe(RuntimeEvent(1001, {"future": True}))
            event_id = run.observe(
                RuntimeEvent(
                    1001,
                    {"future": True, "extension_field": "preserved"},
                    attributes={"compatibility": "optional"},
                )
            )
            run.complete(RunOutcome(Outcome.SUCCESS))
            events = list(experience.repository.events())
            unknown = next(event for event in events if event.event_id == event_id)
            self.assertEqual(unknown.event_type, 1001)
            self.assertEqual(unknown.attributes["compatibility"], "optional")
            self.assertEqual(unpack_payload(unknown)["extension_field"], "preserved")
            self.assertEqual(experience.repository.verify(), 3)
            with SQLiteProjection(experience.repository) as projection:
                self.assertEqual(projection.update(), 3)
            experience.close()

    def test_parent_child_registry_and_runtime_shutdown(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            parent = experience.start("parent", agent="agent-1", harness="loop-1")
            child = parent.start_child("delegated", task_id="child-task")
            self.assertEqual(experience.active_run_count, 2)
            self.assertEqual(child.context.parent_run_id, parent.run_id)
            self.assertEqual(child.context.agent_id, "agent-1")
            child.complete(RunOutcome(Outcome.SUCCESS))
            self.assertEqual(experience.active_run_count, 1)
            experience.close()
            self.assertEqual(parent.state, RunState.CANCELLED)
            self.assertEqual(experience.active_run_count, 0)

    def test_context_manager_records_failure_and_releases_session(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            with self.assertRaisesRegex(LookupError, "missing"):
                with experience.start("will fail"):
                    raise LookupError("missing")
            self.assertEqual(experience.active_run_count, 0)
            events = list(experience.repository.events())
            self.assertEqual(
                [event.event_type for event in events],
                [events_pb2.RUN_STARTED, events_pb2.RUN_FAILED],
            )
            self.assertEqual(unpack_payload(events[-1])["outcome"], "failure")
            experience.close()

    def test_protocol_conformance_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            def custom_loop(runtime: object) -> str:
                self.assertIs(runtime, experience)
                run = experience.start("conformance", harness="custom-loop")
                run.observe(RuntimeEvent(events_pb2.NODE_STARTED, {"node_id": "work"}))
                run.complete(RunOutcome(Outcome.SUCCESS))
                return run.run_id

            report = run_protocol_conformance(experience, "custom-loop", custom_loop)
            self.assertTrue(report.passed)
            self.assertEqual(
                {check.status for check in report.checks},
                {ConformanceStatus.PASS},
            )
            experience.close()

    def test_conformance_reports_unsupported_declared_capability(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")
            capabilities = AdapterCapabilities(
                framework="observation-only",
                integration_version="1",
                level=CapabilityLevel.RUN,
                supports_explicit_runs=True,
            )

            def exercise(runtime: object) -> str:
                self.assertIs(runtime, experience)
                run = experience.start("capabilities")
                run.complete(RunOutcome(Outcome.SUCCESS))
                return run.run_id

            report = run_protocol_conformance(
                experience,
                "observation-only",
                exercise,
                capabilities=capabilities,
                requirements=ConformanceRequirements(selection=True),
            )
            status = {check.name: check.status for check in report.checks}
            self.assertEqual(status["capability:explicit_runs"], ConformanceStatus.PASS)
            self.assertEqual(status["capability:selection"], ConformanceStatus.UNSUPPORTED)
            unsupported = next(
                check for check in report.checks if check.name == "capability:selection"
            )
            self.assertEqual(
                unsupported.reason_code,
                ConformanceReasonCode.CAPABILITY_UNSUPPORTED,
            )
            payload = json.loads(report.to_json(indent=None))
            self.assertEqual(payload["schema_version"], "0.2")
            self.assertFalse(payload["passed"])
            self.assertEqual(
                next(
                    check["reason_code"]
                    for check in payload["checks"]
                    if check["name"] == "capability:selection"
                ),
                "CAPABILITY_UNSUPPORTED",
            )
            self.assertFalse(report.passed)
            experience.close()

    def test_conformance_exercise_failure_has_stable_reason_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            def fail(runtime: object) -> str:
                self.assertIs(runtime, experience)
                raise LookupError("broken integration")

            report = run_protocol_conformance(experience, "broken", fail)
            self.assertFalse(report.passed)
            self.assertEqual(report.checks[0].status, ConformanceStatus.FAIL)
            self.assertEqual(
                report.checks[0].reason_code,
                ConformanceReasonCode.EXERCISE_RAISED,
            )
            self.assertEqual(report.to_dict()["integration"], "broken")
            experience.close()

    def test_async_tasks_use_same_protocol_without_context_crosstalk(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            experience = agent_experience(Path(directory) / "experience")

            async def execute(index: int) -> str:
                run = experience.start(f"async-{index}", task_id=f"async-{index}")
                await asyncio.sleep(0)
                run.observe(RuntimeEvent(events_pb2.NODE_STARTED, {"index": index}))
                await asyncio.sleep(0)
                run.complete(RunOutcome(Outcome.SUCCESS, result=index))
                return run.run_id

            async def gather_runs() -> list[str]:
                return list(await asyncio.gather(*(execute(index) for index in range(16))))

            run_ids = asyncio.run(gather_runs())
            self.assertEqual(len(set(run_ids)), 16)
            self.assertEqual(experience.active_run_count, 0)
            events = list(experience.repository.events())
            self.assertEqual({event.run_id for event in events}, set(run_ids))
            experience.close()


if __name__ == "__main__":
    unittest.main()
