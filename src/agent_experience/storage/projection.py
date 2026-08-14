"""Projection replay and durable watermark primitives."""

from __future__ import annotations

import os
import struct
from collections.abc import Callable

from agent_experience.schema import events_pb2

from .repository import Repository

_WATERMARK = struct.Struct(">Q")


class ProjectionRunner:
    """Replay repository events into an idempotent projection callback."""

    def __init__(self, repository: Repository, name: str) -> None:
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
        if not name or any(character not in allowed for character in name):
            raise ValueError("projection name may contain lowercase letters, digits, '-' and '_'")
        self.repository = repository
        self.path = repository.path / "index" / f"{name}.watermark"

    @property
    def watermark(self) -> int:
        """Return the last durably projected event sequence."""

        if not self.path.exists():
            return 0
        raw = self.path.read_bytes()
        if len(raw) != _WATERMARK.size:
            raise ValueError(f"invalid projection watermark: {self.path}")
        return int(_WATERMARK.unpack(raw)[0])

    def run(self, project: Callable[[events_pb2.EventEnvelope], None]) -> int:
        """Project remaining events, committing the watermark after every callback."""

        watermark = self.watermark
        for event in self.repository.events(after_sequence=watermark):
            project(event)
            self._commit(event.sequence_number)
            watermark = event.sequence_number
        return watermark

    def _commit(self, sequence: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("wb") as file:
            file.write(_WATERMARK.pack(sequence))
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(self.path)
