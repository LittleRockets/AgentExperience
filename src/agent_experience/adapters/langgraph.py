"""LangGraph event normalization independent of optional runtime imports."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from agent_experience.schema import events_pb2
from agent_experience.security import RedactionPolicy

from ._utils import get_value, object_summary
from .base import AdapterCapabilities, CapabilityLevel, EventSink

LANGGRAPH_CAPABILITIES = AdapterCapabilities(
    framework="langgraph",
    integration_version="1.x",
    level=CapabilityLevel.GRAPH,
    observes_runs=True,
    observes_graph_nodes=True,
    observes_routes=True,
    observes_interrupts=True,
    supports_explicit_runs=True,
    supports_selection=True,
    supports_feedback=True,
    supports_delegation=True,
    supports_async=True,
    limitations=(
        "Typed event streaming requires LangGraph 1.2 or newer.",
        "Outcome evaluation must be supplied by the application.",
    ),
)


class LangGraphEventBridge:
    """Consume LangGraph tasks/updates/interrupts without retaining full graph state."""

    capabilities = LANGGRAPH_CAPABILITIES

    def __init__(
        self,
        repository: EventSink,
        *,
        run_id: str | None = None,
        producer: str = "langgraph",
        redaction: RedactionPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.run_id = run_id or str(uuid.uuid4())
        self.producer = producer
        self.policy = redaction or RedactionPolicy()
        self._tasks: dict[str, str] = {}

    def consume(self, event: Mapping[str, Any] | object) -> None:
        """Normalize one typed stream part or mapping-shaped stream event."""

        event_type = get_value(event, "type", "")
        namespace = tuple(get_value(event, "ns", ()) or ())
        data = get_value(event, "data", {})
        if event_type == "tasks":
            self._consume_task(data, namespace)
        elif event_type == "updates":
            self._consume_update(data, namespace)
        elif event_type == "checkpoints":
            self._append(
                events_pb2.ARTIFACT_PRODUCED,
                {
                    "artifact_type": "langgraph-checkpoint",
                    "namespace": list(namespace),
                    "checkpoint": object_summary(data, self.policy),
                },
            )

    def interrupt(self, event: object) -> None:
        """Record a public GraphInterruptEvent from LangGraph 1.1+."""

        self._append(
            events_pb2.APPROVAL_REQUESTED,
            {
                "kind": "langgraph-interrupt",
                "checkpoint_id": str(get_value(event, "checkpoint_id", "")),
                "checkpoint_namespace": list(get_value(event, "checkpoint_ns", ()) or ()),
                "interrupts": object_summary(get_value(event, "interrupts", ()), self.policy),
            },
        )

    def resume(self, event: object) -> None:
        """Record a graph resume as an approval/input decision."""

        self._append(
            events_pb2.APPROVAL_DECIDED,
            {
                "kind": "langgraph-resume",
                "checkpoint_id": str(get_value(event, "checkpoint_id", "")),
                "checkpoint_namespace": list(get_value(event, "checkpoint_ns", ()) or ()),
            },
        )

    def _consume_task(self, data: object, namespace: tuple[str, ...]) -> None:
        task_id = str(get_value(data, "id", ""))
        name = str(get_value(data, "name", "unknown"))
        error = get_value(data, "error")
        is_result = (
            error is not None
            or get_value(data, "result") is not None
            or get_value(data, "interrupts")
        )
        if not is_result:
            event = self._append(
                events_pb2.NODE_STARTED,
                {
                    "task_id": task_id,
                    "node_id": name,
                    "namespace": list(namespace),
                    "input": object_summary(get_value(data, "input"), self.policy),
                    "triggers": object_summary(get_value(data, "triggers", ()), self.policy),
                },
            )
            self._tasks[task_id] = event.event_id
            return
        event_type = events_pb2.NODE_FAILED if error is not None else events_pb2.NODE_COMPLETED
        self._append(
            event_type,
            {
                "task_id": task_id,
                "node_id": name,
                "namespace": list(namespace),
                "result": object_summary(get_value(data, "result"), self.policy),
                "error": object_summary(error, self.policy),
                "interrupts": object_summary(get_value(data, "interrupts", ()), self.policy),
            },
            causation_id=self._tasks.get(task_id, ""),
        )

    def _consume_update(self, data: object, namespace: tuple[str, ...]) -> None:
        if not isinstance(data, Mapping):
            return
        for route, update in data.items():
            self._append(
                events_pb2.ROUTE_SELECTED,
                {
                    "route": str(route),
                    "namespace": list(namespace),
                    "update": object_summary(update, self.policy),
                },
            )

    def _append(self, event_type: int, payload: dict[str, Any], causation_id: str = "") -> Any:
        return self.repository.append_event(
            event_type,
            run_id=self.run_id,
            producer=self.producer,
            payload=payload,
            correlation_id=self.run_id,
            causation_id=causation_id,
        )


def create_langgraph_callback(bridge: LangGraphEventBridge) -> object:
    """Create a LangGraph 1.1+ lifecycle callback with delayed optional import."""

    try:
        from langgraph.callbacks import GraphCallbackHandler
    except ImportError as error:
        raise ImportError(
            "LangGraph support requires: pip install 'agent-experience[langgraph]'"
        ) from error

    class AgentExperienceGraphCallback(GraphCallbackHandler):
        def on_interrupt(self, event: Any) -> None:
            bridge.interrupt(event)

        def on_resume(self, event: Any) -> None:
            bridge.resume(event)

    return AgentExperienceGraphCallback()
