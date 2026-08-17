"""Reusable conformance checks for v0.2 Harness protocol integrations."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from agent_experience.adapters.base import AdapterCapabilities
from agent_experience.events.factory import unpack_payload
from agent_experience.runtime import ExperienceRuntime
from agent_experience.schema import events_pb2


class ConformanceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNSUPPORTED = "unsupported"
    INCONCLUSIVE = "inconclusive"


class ConformanceReasonCode(str, Enum):
    EXERCISE_RAISED = "EXERCISE_RAISED"
    RUN_ID_MISSING = "RUN_ID_MISSING"
    START_COUNT_MISMATCH = "START_COUNT_MISMATCH"
    TERMINAL_COUNT_MISMATCH = "TERMINAL_COUNT_MISMATCH"
    EVENT_AFTER_TERMINAL = "EVENT_AFTER_TERMINAL"
    CORRELATION_MISSING = "CORRELATION_MISSING"
    PAYLOAD_INTEGRITY_FAILED = "PAYLOAD_INTEGRITY_FAILED"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    CAPABILITY_UNDECLARED = "CAPABILITY_UNDECLARED"
    BEHAVIOR_EVIDENCE_MISSING = "BEHAVIOR_EVIDENCE_MISSING"


@dataclass(frozen=True, slots=True)
class ConformanceCheck:
    name: str
    status: ConformanceStatus
    detail: str = ""
    reason_code: ConformanceReasonCode | None = None


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    integration: str
    run_id: str
    checks: tuple[ConformanceCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.status is ConformanceStatus.PASS for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        """Return a stable, JSON-compatible report without Python enum objects."""

        return {
            "schema_version": "0.2",
            "integration": self.integration,
            "run_id": self.run_id,
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "detail": check.detail,
                    "reason_code": check.reason_code.value if check.reason_code else None,
                }
                for check in self.checks
            ],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the stable report deterministically for CI artifacts."""

        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass(frozen=True, slots=True)
class ConformanceRequirements:
    """Capabilities a Harness integration promises for one conformance run."""

    explicit_runs: bool = True
    selection: bool = False
    feedback: bool = False
    delegation: bool = False
    async_execution: bool = False


def run_protocol_conformance(
    runtime: ExperienceRuntime,
    integration: str,
    exercise: Callable[[ExperienceRuntime], str],
    *,
    capabilities: AdapterCapabilities | None = None,
    requirements: ConformanceRequirements | None = None,
) -> ConformanceReport:
    """Exercise an integration and validate its persisted v0.2 lifecycle evidence.

    ``exercise`` must run one complete/cancelled Harness task and return its protocol ``run_id``.
    The function intentionally validates persisted facts rather than trusting adapter return values.
    """

    required = requirements or ConformanceRequirements()
    capability_checks = _capability_checks(capabilities, required)
    before = runtime.repository.last_sequence
    try:
        run_id = exercise(runtime)
    except BaseException as error:
        return ConformanceReport(
            integration,
            "",
            (
                *capability_checks,
                ConformanceCheck(
                    "exercise",
                    ConformanceStatus.FAIL,
                    f"integration exercise raised {type(error).__name__}: {error}",
                    ConformanceReasonCode.EXERCISE_RAISED,
                ),
            ),
        )
    all_events = list(runtime.repository.events(after_sequence=before))
    events = [
        event
        for event in all_events
        if event.run_id == run_id
    ]
    types = [event.event_type for event in events]
    terminal = {
        events_pb2.RUN_COMPLETED,
        events_pb2.RUN_FAILED,
        events_pb2.RUN_CANCELLED,
    }
    terminal_indexes = [index for index, value in enumerate(types) if value in terminal]
    checks = [
        *capability_checks,
        ConformanceCheck(
            "run_id",
            ConformanceStatus.PASS if bool(run_id) else ConformanceStatus.FAIL,
            "integration returned a non-empty run id" if run_id else "run id is empty",
            None if run_id else ConformanceReasonCode.RUN_ID_MISSING,
        ),
        ConformanceCheck(
            "started",
            ConformanceStatus.PASS
            if types.count(events_pb2.RUN_STARTED) == 1
            else ConformanceStatus.FAIL,
            f"RUN_STARTED count={types.count(events_pb2.RUN_STARTED)}",
            None
            if types.count(events_pb2.RUN_STARTED) == 1
            else ConformanceReasonCode.START_COUNT_MISMATCH,
        ),
        ConformanceCheck(
            "terminal",
            ConformanceStatus.PASS if len(terminal_indexes) == 1 else ConformanceStatus.FAIL,
            f"terminal event count={len(terminal_indexes)}",
            None
            if len(terminal_indexes) == 1
            else ConformanceReasonCode.TERMINAL_COUNT_MISMATCH,
        ),
        ConformanceCheck(
            "terminal_order",
            ConformanceStatus.PASS
            if terminal_indexes
            and all(
                value == events_pb2.OUTCOME_EVALUATED
                for value in types[terminal_indexes[0] + 1 :]
            )
            else ConformanceStatus.FAIL,
            "only terminal evaluation evidence may follow the terminal lifecycle event",
            None
            if terminal_indexes
            and all(
                value == events_pb2.OUTCOME_EVALUATED
                for value in types[terminal_indexes[0] + 1 :]
            )
            else ConformanceReasonCode.EVENT_AFTER_TERMINAL,
        ),
        ConformanceCheck(
            "correlation",
            ConformanceStatus.PASS
            if events and all(event.correlation_id for event in events)
            else ConformanceStatus.FAIL,
            "every event must carry a correlation id",
            None
            if events and all(event.correlation_id for event in events)
            else ConformanceReasonCode.CORRELATION_MISSING,
        ),
    ]
    for event in events:
        try:
            unpack_payload(event)
        except ValueError as error:
            checks.append(
                ConformanceCheck(
                    "payload_integrity",
                    ConformanceStatus.FAIL,
                    str(error),
                    ConformanceReasonCode.PAYLOAD_INTEGRITY_FAILED,
                )
            )
            break
    else:
        checks.append(
            ConformanceCheck(
                "payload_integrity",
                ConformanceStatus.PASS,
                f"validated {len(events)} event payloads",
            )
        )
    checks.extend(
        _behavior_checks(events, all_events, run_id, required, capabilities)
    )
    return ConformanceReport(integration, run_id, tuple(checks))


def _capability_checks(
    capabilities: AdapterCapabilities | None,
    requirements: ConformanceRequirements,
) -> list[ConformanceCheck]:
    promised = {
        "explicit_runs": requirements.explicit_runs,
        "selection": requirements.selection,
        "feedback": requirements.feedback,
        "delegation": requirements.delegation,
        "async_execution": requirements.async_execution,
    }
    if capabilities is None:
        return [
            ConformanceCheck(
                f"capability:{name}",
                ConformanceStatus.INCONCLUSIVE,
                "integration did not provide a machine-readable capability declaration",
                ConformanceReasonCode.CAPABILITY_UNDECLARED,
            )
            for name, required in promised.items()
            if required and name != "explicit_runs"
        ]
    supported = {
        "explicit_runs": capabilities.supports_explicit_runs,
        "selection": capabilities.supports_selection,
        "feedback": capabilities.supports_feedback,
        "delegation": capabilities.supports_delegation,
        "async_execution": capabilities.supports_async,
    }
    return [
        ConformanceCheck(
            f"capability:{name}",
            ConformanceStatus.PASS if supported[name] else ConformanceStatus.UNSUPPORTED,
            f"required={required}, declared={supported[name]}",
            None if supported[name] else ConformanceReasonCode.CAPABILITY_UNSUPPORTED,
        )
        for name, required in promised.items()
        if required
    ]


def _behavior_checks(
    events: list[events_pb2.EventEnvelope],
    all_events: list[events_pb2.EventEnvelope],
    run_id: str,
    requirements: ConformanceRequirements,
    capabilities: AdapterCapabilities | None,
) -> list[ConformanceCheck]:
    checks: list[ConformanceCheck] = []
    operations = {event.attributes.get("protocol_operation", "") for event in events}
    declared = {
        "selection": capabilities.supports_selection if capabilities is not None else None,
        "feedback": capabilities.supports_feedback if capabilities is not None else None,
        "delegation": capabilities.supports_delegation if capabilities is not None else None,
    }
    observed = {
        "selection": "select" in operations,
        "feedback": "feedback" in operations,
        "delegation": any(
            _payload_parent_run_id(event) == run_id
            for event in all_events
            if event.event_type == events_pb2.RUN_STARTED and event.run_id != run_id
        ),
    }
    required = {
        "selection": requirements.selection,
        "feedback": requirements.feedback,
        "delegation": requirements.delegation,
    }
    for name, is_required in required.items():
        if not is_required or declared[name] is False:
            continue
        if observed[name]:
            status = ConformanceStatus.PASS
            detail = f"observed persisted {name} protocol evidence"
        elif declared[name] is None:
            status = ConformanceStatus.INCONCLUSIVE
            detail = f"no declaration or persisted {name} evidence"
        else:
            status = ConformanceStatus.FAIL
            detail = f"declared {name} support but no persisted evidence was observed"
        reason_code = (
            None
            if status is ConformanceStatus.PASS
            else ConformanceReasonCode.CAPABILITY_UNDECLARED
            if status is ConformanceStatus.INCONCLUSIVE
            else ConformanceReasonCode.BEHAVIOR_EVIDENCE_MISSING
        )
        checks.append(ConformanceCheck(f"behavior:{name}", status, detail, reason_code))
    return checks


def _payload_parent_run_id(event: events_pb2.EventEnvelope) -> str:
    try:
        return str(unpack_payload(event).get("parent_run_id", ""))
    except ValueError:
        return ""
