"""Repository lifecycle and canonical event persistence."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from google.protobuf import message

from agent_experience.events.factory import create_event, unpack_payload
from agent_experience.schema import events_pb2

from .event_log import Durability, EventLog, LogRecord

_REPOSITORY_ID_FILE = "repository.id"
_EVENT_LOG_FILE = "logs/events-000001.bin"
_EVENT_RECORD_TYPE = 1


class Repository:
    """A single-writer local AgentExperience repository.

    Repository creation is explicit. Existing repositories retain their UUID and resume event
    sequence allocation from the recovered event log.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        durability: Durability = Durability.RUN_DURABLE,
    ) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._repository_uuid = self._load_or_create_id()
        self._sequence_lock = threading.Lock()
        self._log = EventLog(
            self.path / _EVENT_LOG_FILE,
            self._repository_uuid.bytes,
            durability=durability,
        )

    @property
    def repository_id(self) -> str:
        """Stable UUID identifying this repository."""

        return str(self._repository_uuid)

    @property
    def last_sequence(self) -> int:
        """Highest committed event sequence."""

        return self._log.last_sequence

    def append_event(
        self,
        event_type: int,
        *,
        run_id: str,
        producer: str,
        payload: Mapping[str, Any] | message.Message | None = None,
        attributes: Mapping[str, str] | None = None,
        correlation_id: str = "",
        causation_id: str = "",
        durability: Durability | None = None,
    ) -> events_pb2.EventEnvelope:
        """Construct, serialize, and atomically append one canonical event."""

        with self._sequence_lock:
            sequence = self._log.last_sequence + 1
            envelope = create_event(
                event_type=event_type,
                repository_id=self.repository_id,
                run_id=run_id,
                sequence_number=sequence,
                producer=producer,
                payload=payload,
                attributes=attributes,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            self._log.append(
                envelope.SerializeToString(deterministic=True),
                sequence_number=sequence,
                record_type=_EVENT_RECORD_TYPE,
                durability=durability,
            )
            return envelope

    def events(self, *, after_sequence: int = 0) -> Iterator[events_pb2.EventEnvelope]:
        """Replay validated events after the given projection watermark."""

        for record in self._log.records():
            if record.sequence_number <= after_sequence:
                continue
            yield self._decode_event(record)

    def verify(self) -> int:
        """Validate all frames, envelopes, sequence numbers, repository IDs, and payload hashes."""

        count = 0
        for envelope in self.events():
            unpack_payload(envelope)
            count += 1
        return count

    def close(self) -> None:
        """Close the repository event log."""

        self._log.close()

    def __enter__(self) -> Repository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _load_or_create_id(self) -> uuid.UUID:
        path = self.path / _REPOSITORY_ID_FILE
        if path.exists():
            value = path.read_text(encoding="ascii").strip()
            try:
                return uuid.UUID(value)
            except ValueError as error:
                raise ValueError(f"invalid repository ID in {path}") from error
        repository_id = uuid.uuid4()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(f"{repository_id}\n", encoding="ascii")
        temporary.replace(path)
        return repository_id

    def _decode_event(self, record: LogRecord) -> events_pb2.EventEnvelope:
        if record.record_type != _EVENT_RECORD_TYPE:
            raise ValueError(f"unsupported log record type: {record.record_type}")
        envelope = events_pb2.EventEnvelope.FromString(record.payload)
        if envelope.sequence_number != record.sequence_number:
            raise ValueError("event and frame sequence numbers differ")
        if envelope.repository_id != self.repository_id:
            raise ValueError("event belongs to a different repository")
        return envelope
