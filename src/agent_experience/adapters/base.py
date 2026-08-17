"""Framework adapter capability declarations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Protocol

from agent_experience.schema import events_pb2


class EventSink(Protocol):
    """Minimal gateway required by framework signal translators."""

    def append_event(self, event_type: int, **kwargs: Any) -> events_pb2.EventEnvelope: ...


class CapabilityLevel(IntEnum):
    """Highest reliable observation level provided by an adapter."""

    RUN = 0
    ACTION = 1
    GRAPH = 2
    OUTCOME = 3


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    """Machine-readable adapter support advertised at integration time."""

    framework: str
    integration_version: str
    level: CapabilityLevel
    observes_runs: bool = False
    observes_models: bool = False
    observes_tools: bool = False
    observes_graph_nodes: bool = False
    observes_routes: bool = False
    observes_interrupts: bool = False
    supports_advice: bool = False
    supports_replay: bool = False
    limitations: tuple[str, ...] = ()
    protocol_version: str = "0.2"
    supports_explicit_runs: bool = False
    supports_selection: bool = False
    supports_feedback: bool = False
    supports_delegation: bool = False
    supports_async: bool = False

    def __post_init__(self) -> None:
        if not self.framework:
            raise ValueError("adapter framework must not be empty")
        if not self.integration_version:
            raise ValueError("adapter integration_version must not be empty")
        if self.protocol_version != "0.2":
            raise ValueError(f"unsupported Experience Protocol version: {self.protocol_version}")
        if self.supports_feedback and not self.supports_explicit_runs:
            raise ValueError("feedback support requires explicit run support")
        if self.supports_delegation and not self.supports_explicit_runs:
            raise ValueError("delegation support requires explicit run support")
