"""Factories for canonical, integrity-protected event envelopes."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Mapping
from typing import Any, cast

from google.protobuf import any_pb2, json_format, message, struct_pb2, timestamp_pb2

from agent_experience.schema import events_pb2

_KNOWN_EVENT_TYPES = frozenset(events_pb2.EventType.values())
_OPTIONAL_COMPATIBILITY = "optional"


def is_known_event_type(event_type: int) -> bool:
    """Return whether this SDK version understands the event's lifecycle semantics."""

    return event_type in _KNOWN_EVENT_TYPES


def validate_event_compatibility(
    event_type: int, attributes: Mapping[str, str] | None = None
) -> None:
    """Preserve explicitly optional unknown events and reject unknown critical semantics."""

    if event_type == events_pb2.EVENT_TYPE_UNSPECIFIED:
        raise ValueError("event_type must be specified")
    if is_known_event_type(event_type):
        return
    compatibility = (attributes or {}).get("compatibility", "")
    if compatibility != _OPTIONAL_COMPATIBILITY:
        raise ValueError(
            f"unknown critical event type {event_type}; only events marked "
            "compatibility='optional' may be preserved"
        )


def create_event(
    *,
    event_type: int,
    repository_id: str,
    run_id: str,
    sequence_number: int,
    producer: str,
    payload: Mapping[str, Any] | message.Message | None = None,
    attributes: Mapping[str, str] | None = None,
    correlation_id: str = "",
    causation_id: str = "",
) -> events_pb2.EventEnvelope:
    """Create a canonical event whose payload hash covers deterministic payload bytes."""

    validate_event_compatibility(event_type, attributes)
    if sequence_number <= 0:
        raise ValueError("sequence_number must be positive")
    if payload is None or isinstance(payload, Mapping):
        value: message.Message = struct_pb2.Struct()
        json_format.ParseDict(dict(payload or {}), value)
    else:
        value = payload
    packed = any_pb2.Any()
    packed.Pack(value)
    payload_bytes = value.SerializeToString(deterministic=True)
    timestamp = timestamp_pb2.Timestamp()
    timestamp.FromNanoseconds(time.time_ns())
    return events_pb2.EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=cast(Any, event_type),
        schema_version=1,
        timestamp=timestamp,
        repository_id=repository_id,
        run_id=run_id,
        sequence_number=sequence_number,
        correlation_id=correlation_id or run_id,
        causation_id=causation_id,
        producer=producer,
        payload=packed,
        payload_hash=hashlib.sha256(payload_bytes).digest(),
        attributes=dict(attributes or {}),
    )


def unpack_payload(envelope: events_pb2.EventEnvelope) -> dict[str, Any]:
    """Validate and unpack a supported strongly typed event payload."""

    from agent_experience.schema import experience_pb2, package_pb2

    if envelope.payload.Is(struct_pb2.Struct.DESCRIPTOR):
        value: message.Message = struct_pb2.Struct()
    elif envelope.payload.Is(experience_pb2.ExperienceDefinition.DESCRIPTOR):
        value = experience_pb2.ExperienceDefinition()
    elif envelope.payload.Is(experience_pb2.EvaluationEvent.DESCRIPTOR):
        value = experience_pb2.EvaluationEvent()
    elif envelope.payload.Is(experience_pb2.BenefitMeasurement.DESCRIPTOR):
        value = experience_pb2.BenefitMeasurement()
    elif envelope.payload.Is(package_pb2.ExperiencePackageManifest.DESCRIPTOR):
        value = package_pb2.ExperiencePackageManifest()
    else:
        raise ValueError(f"unsupported event payload type: {envelope.payload.type_url}")
    if not envelope.payload.Unpack(value):
        raise ValueError(f"invalid event payload: {envelope.payload.type_url}")
    payload_bytes = value.SerializeToString(deterministic=True)
    if hashlib.sha256(payload_bytes).digest() != envelope.payload_hash:
        raise ValueError("event payload hash mismatch")
    return json_format.MessageToDict(value, preserving_proto_field_name=True)
