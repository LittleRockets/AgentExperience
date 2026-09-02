"""Framework-neutral v0.2 Experience Protocol contracts and run session."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from agent_experience.outcome import Evaluation, Outcome
from agent_experience.schema import events_pb2

if TYPE_CHECKING:
    from agent_experience.runtime import ExperienceRuntime

PROTOCOL_API_VERSION = "0.3"


def _frozen_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class RunContext:
    """Immutable identity and capability snapshot for one Harness run."""

    run_id: str
    task_id: str = ""
    agent_id: str = ""
    harness_id: str = ""
    model_id: str = ""
    parent_run_id: str = ""
    environment: Mapping[str, Any] = field(default_factory=dict)
    budget: Mapping[str, Any] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    started_ns: int = field(default_factory=time.time_ns)

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id must not be empty")
        object.__setattr__(self, "environment", _frozen_mapping(self.environment))
        object.__setattr__(self, "budget", _frozen_mapping(self.budget))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))
        object.__setattr__(self, "tools", tuple(self.tools))


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """One normalized piece of structured Runtime Evidence."""

    event_type: int
    payload: Mapping[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    causation_id: str = ""
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type == events_pb2.EVENT_TYPE_UNSPECIFIED:
            raise ValueError("event_type must be specified")
        object.__setattr__(self, "payload", _frozen_mapping(self.payload))
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True, slots=True)
class HarnessState:
    """Immutable state snapshot supplied by a Harness at a selection point."""

    task: str
    goal: str = ""
    framework: str = ""
    model_id: str = ""
    available_tools: frozenset[str] = frozenset()
    environment: Mapping[str, Any] = field(default_factory=dict)
    budget: Mapping[str, Any] = field(default_factory=dict)
    harness_policy: Mapping[str, Any] = field(default_factory=dict)
    previous_attempts: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.task:
            raise ValueError("task must not be empty")
        object.__setattr__(self, "available_tools", frozenset(self.available_tools))
        object.__setattr__(self, "environment", _frozen_mapping(self.environment))
        object.__setattr__(self, "budget", _frozen_mapping(self.budget))
        object.__setattr__(self, "harness_policy", _frozen_mapping(self.harness_policy))
        object.__setattr__(
            self,
            "previous_attempts",
            tuple(_frozen_mapping(value) for value in self.previous_attempts),
        )


class SelectionDecision(str, Enum):
    SELECTED = "selected"
    REJECTED = "rejected"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Explainable selection output; it never controls the Harness."""

    decision: SelectionDecision
    experience_id: str = ""
    revision_id: str = ""
    confidence: float = 0.0
    expected_benefit: float = 0.0
    cost: float = 0.0
    risk: str = "unknown"
    reason_codes: tuple[str, ...] = ()
    summary: str = ""
    steps: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("selection confidence must be between 0 and 1")
        if self.decision is SelectionDecision.SELECTED and not self.experience_id:
            raise ValueError("selected result requires an experience_id")


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Quality, cost and risk signals reported by a Harness."""

    status: Outcome
    result: Any = None
    reward: float | None = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    tokens: int = 0
    latency_ms: float = 0.0
    tool_cost: float = 0.0
    risk: str = "unknown"

    def __post_init__(self) -> None:
        if self.tokens < 0 or self.latency_ms < 0 or self.tool_cost < 0:
            raise ValueError("outcome cost metrics must not be negative")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


class RunState(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperienceRun:
    """Thread-safe explicit session owned by one external Harness run."""

    def __init__(
        self,
        runtime: ExperienceRuntime,
        context: RunContext,
        *,
        started_event_id: str,
        started_perf_ns: int,
    ) -> None:
        self._runtime = runtime
        self.context = context
        self._started_event_id = started_event_id
        self._started_perf_ns = started_perf_ns
        self._state = RunState.RUNNING
        self._lock = threading.RLock()

    @property
    def run_id(self) -> str:
        return self.context.run_id

    @property
    def state(self) -> RunState:
        with self._lock:
            return self._state

    def observe(self, event: RuntimeEvent) -> str:
        """Append normalized evidence and return its immutable event id."""

        envelope = self.append_event(
            event.event_type,
            payload=event.payload,
            attributes=event.attributes,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
        )
        return envelope.event_id

    def append_event(
        self,
        event_type: int,
        *,
        run_id: str = "",
        producer: str = "",
        payload: Mapping[str, Any] | None = None,
        attributes: Mapping[str, str] | None = None,
        correlation_id: str = "",
        causation_id: str = "",
        **unsupported: Any,
    ) -> events_pb2.EventEnvelope:
        """Implement the bounded EventSink used by framework signal translators.

        Adapters may choose their producer identity, but cannot write into another session or pass
        storage-specific options through this protocol boundary.
        """

        with self._lock:
            self._require_running("append an event to")
            if run_id and run_id != self.run_id:
                raise ValueError("adapter event run_id does not match the bound ExperienceRun")
            if unsupported:
                names = ", ".join(sorted(unsupported))
                raise TypeError(f"unsupported adapter event options: {names}")
            return self._runtime.repository.append_event(
                event_type,
                run_id=self.run_id,
                producer=producer or "agent-experience-protocol/v0.2",
                payload=self._runtime.redaction.sanitize(dict(payload or {})),
                attributes=dict(attributes or {}),
                correlation_id=correlation_id or self.run_id,
                causation_id=causation_id or self._started_event_id,
            )

    def select(self, state: HarnessState, *, limit: int = 5) -> tuple[SelectionResult, ...]:
        """Request explainable advice without transferring Loop ownership."""

        with self._lock:
            self._require_running("select")
            return self._runtime._select_for_run(self, state, limit=limit)

    def start_child(
        self,
        task: Any,
        *,
        task_id: str = "",
        agent: str | None = None,
        harness: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExperienceRun:
        """Start a delegated run with an explicit, auditable parent relationship."""

        with self._lock:
            self._require_running("start a child from")
            return self._runtime.start(
                task,
                task_id=task_id,
                agent=agent if agent is not None else self.context.agent_id,
                harness=harness if harness is not None else self.context.harness_id,
                model_id=self.context.model_id,
                environment=dict(self.context.environment),
                budget=dict(self.context.budget),
                tools=self.context.tools,
                metadata=dict(metadata or {}),
                parent_run_id=self.run_id,
            )

    def feedback(
        self,
        outcome: RunOutcome,
        *,
        evaluation: Evaluation | None = None,
        experience_id: str = "",
        revision_id: str = "",
        accepted: bool | None = None,
    ) -> str:
        """Record an intermediate outcome or experience-use decision."""

        with self._lock:
            self._require_running("feedback")
            event = self._runtime.repository.append_event(
                events_pb2.EXPERIENCE_APPLIED if accepted else events_pb2.OUTCOME_EVALUATED,
                run_id=self.run_id,
                producer="agent-experience-protocol/v0.2",
                payload=self._runtime._outcome_payload(
                    outcome,
                    evaluation,
                    experience_id=experience_id,
                    revision_id=revision_id,
                    accepted=accepted,
                ),
                attributes={"protocol_operation": "feedback"},
                correlation_id=self.run_id,
                causation_id=self._started_event_id,
            )
            return event.event_id

    def complete(
        self, outcome: RunOutcome, *, evaluation: Evaluation | None = None
    ) -> None:
        """Finish the run exactly once and optionally record evaluation evidence."""

        with self._lock:
            self._require_running("complete")
            terminal_type = (
                events_pb2.RUN_FAILED
                if outcome.status is Outcome.FAILURE
                else events_pb2.RUN_COMPLETED
            )
            terminal = self._runtime.repository.append_event(
                terminal_type,
                run_id=self.run_id,
                producer="agent-experience-protocol/v0.2",
                payload={
                    **self._runtime._outcome_payload(outcome, None),
                    "duration_ns": time.perf_counter_ns() - self._started_perf_ns,
                },
                correlation_id=self.run_id,
                causation_id=self._started_event_id,
            )
            if evaluation is not None:
                self._runtime.repository.append_event(
                    events_pb2.OUTCOME_EVALUATED,
                    run_id=self.run_id,
                    producer="agent-experience-protocol/v0.2",
                    payload=self._runtime._outcome_payload(outcome, evaluation),
                    correlation_id=self.run_id,
                    causation_id=terminal.event_id,
                )
            self._state = (
                RunState.FAILED if outcome.status is Outcome.FAILURE else RunState.COMPLETED
            )
            self._runtime._release_session(self.run_id)
            if outcome.status is Outcome.SUCCESS and evaluation is not None:
                self._runtime._enqueue_consolidation()

    def cancel(self, reason: str = "") -> None:
        """Cancel a running session; cancellation is terminal and idempotency is explicit."""

        with self._lock:
            self._require_running("cancel")
            self._runtime.repository.append_event(
                events_pb2.RUN_CANCELLED,
                run_id=self.run_id,
                producer="agent-experience-protocol/v0.2",
                payload={
                    "reason": self._runtime.redaction.sanitize(reason),
                    "duration_ns": time.perf_counter_ns() - self._started_perf_ns,
                },
                correlation_id=self.run_id,
                causation_id=self._started_event_id,
            )
            self._state = RunState.CANCELLED
            self._runtime._release_session(self.run_id)

    def __enter__(self) -> ExperienceRun:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type
        del traceback
        if self.state is not RunState.RUNNING:
            return
        if isinstance(exc, BaseException):
            self.complete(
                RunOutcome(
                    Outcome.FAILURE,
                    result={"error_type": type(exc).__name__, "error": str(exc)},
                )
            )
            return
        self.cancel("experience run context exited without an explicit outcome")

    def _require_running(self, operation: str) -> None:
        if self._state is not RunState.RUNNING:
            raise RuntimeError(f"cannot {operation} a {self._state.value} experience run")
