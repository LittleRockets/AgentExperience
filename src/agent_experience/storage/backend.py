"""Stable extension protocol for future remote or distributed storage backends."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from agent_experience.schema import events_pb2


class EventBackend(Protocol):
    """Ordered event backend contract; implementations must enforce single sequence ownership."""

    @property
    def last_sequence(self) -> int: ...

    def append(self, envelope: events_pb2.EventEnvelope) -> None: ...

    def events(self, *, after_sequence: int = 0) -> Iterator[events_pb2.EventEnvelope]: ...


class DistributedBackendNotConfigured(RuntimeError):
    """Raised when callers request scale-out behavior without an explicit backend."""
