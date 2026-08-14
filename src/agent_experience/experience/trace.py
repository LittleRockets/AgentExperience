"""Reconstruct auditable run traces from canonical events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2
from agent_experience.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class TraceEntry:
    event: events_pb2.EventEnvelope
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RunTrace:
    run_id: str
    entries: tuple[TraceEntry, ...]

    def is_eligible(self, minimum_confidence: float = 0.8) -> bool:
        completed = any(
            entry.event.event_type == events_pb2.RUN_COMPLETED for entry in self.entries
        )
        outcomes = [
            entry.payload
            for entry in self.entries
            if entry.event.event_type == events_pb2.OUTCOME_EVALUATED
        ]
        return bool(
            completed
            and outcomes
            and outcomes[-1].get("outcome") == "success"
            and float(outcomes[-1].get("confidence", 0.0)) >= minimum_confidence
        )

    @property
    def tool_starts(self) -> tuple[TraceEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.event.event_type == events_pb2.TOOL_CALL_STARTED
        )

    @property
    def has_recovery(self) -> bool:
        failed_at = next(
            (
                index
                for index, entry in enumerate(self.entries)
                if entry.event.event_type in (events_pb2.TOOL_CALL_FAILED, events_pb2.NODE_FAILED)
            ),
            None,
        )
        return failed_at is not None and any(
            entry.event.event_type in (events_pb2.TOOL_CALL_COMPLETED, events_pb2.NODE_COMPLETED)
            for entry in self.entries[failed_at + 1 :]
        )


def load_traces(repository: Repository) -> tuple[RunTrace, ...]:
    grouped: dict[str, list[TraceEntry]] = {}
    for event in repository.events():
        if event.run_id:
            grouped.setdefault(event.run_id, []).append(TraceEntry(event, unpack_payload(event)))
    return tuple(RunTrace(run_id, tuple(grouped[run_id])) for run_id in sorted(grouped))
