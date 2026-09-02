from __future__ import annotations

import dataclasses
import inspect
import unittest

import agent_experience
from agent_experience import (
    PROTOCOL_API_VERSION,
    ConformanceRequirements,
    ExperienceRun,
    ExperienceRuntime,
    HarnessState,
    RunContext,
    RunOutcome,
    RuntimeEvent,
    SelectionResult,
)


class ProtocolAPISnapshotTests(unittest.TestCase):
    def test_v0_2_exports_remain_available_in_v0_3(self) -> None:
        expected = {
            "ConformanceCheck",
            "ConformanceReport",
            "ConformanceReasonCode",
            "ConformanceRequirements",
            "ConformanceStatus",
            "ExperienceRun",
            "ExperienceRuntime",
            "HarnessState",
            "PROTOCOL_API_VERSION",
            "RunContext",
            "RunOutcome",
            "RunState",
            "RuntimeEvent",
            "SelectionDecision",
            "SelectionResult",
            "run_protocol_conformance",
        }
        self.assertEqual(PROTOCOL_API_VERSION, "0.3")
        self.assertTrue(expected.issubset(set(agent_experience.__all__)))

    def test_dataclass_field_snapshot(self) -> None:
        expected = {
            RunContext: (
                "run_id",
                "task_id",
                "agent_id",
                "harness_id",
                "model_id",
                "parent_run_id",
                "environment",
                "budget",
                "tools",
                "metadata",
                "started_ns",
            ),
            RuntimeEvent: (
                "event_type",
                "payload",
                "correlation_id",
                "causation_id",
                "attributes",
            ),
            HarnessState: (
                "task",
                "goal",
                "framework",
                "model_id",
                "available_tools",
                "environment",
                "budget",
                "harness_policy",
                "previous_attempts",
            ),
            RunOutcome: (
                "status",
                "result",
                "reward",
                "metrics",
                "tokens",
                "latency_ms",
                "tool_cost",
                "risk",
            ),
            SelectionResult: (
                "decision",
                "experience_id",
                "revision_id",
                "confidence",
                "expected_benefit",
                "cost",
                "risk",
                "reason_codes",
                "summary",
                "steps",
                "evidence",
            ),
            ConformanceRequirements: (
                "explicit_runs",
                "selection",
                "feedback",
                "delegation",
                "async_execution",
            ),
        }
        for model, names in expected.items():
            self.assertEqual(tuple(field.name for field in dataclasses.fields(model)), names)

    def test_method_parameter_snapshot(self) -> None:
        expected = {
            ExperienceRuntime.start: (
                "self",
                "task",
                "agent",
                "harness",
                "metadata",
                "task_id",
                "model_id",
                "environment",
                "budget",
                "tools",
                "parent_run_id",
            ),
            ExperienceRun.observe: ("self", "event"),
            ExperienceRun.select: ("self", "state", "limit"),
            ExperienceRun.feedback: (
                "self",
                "outcome",
                "evaluation",
                "experience_id",
                "revision_id",
                "accepted",
            ),
            ExperienceRun.complete: ("self", "outcome", "evaluation"),
            ExperienceRun.cancel: ("self", "reason"),
            ExperienceRun.start_child: (
                "self",
                "task",
                "task_id",
                "agent",
                "harness",
                "metadata",
            ),
        }
        for method, names in expected.items():
            self.assertEqual(tuple(inspect.signature(method).parameters), names)


if __name__ == "__main__":
    unittest.main()
