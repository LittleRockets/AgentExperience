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
