import datetime

from google.protobuf import any_pb2 as _any_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EVENT_TYPE_UNSPECIFIED: _ClassVar[EventType]
    RUN_STARTED: _ClassVar[EventType]
    RUN_COMPLETED: _ClassVar[EventType]
    RUN_FAILED: _ClassVar[EventType]
    RUN_CANCELLED: _ClassVar[EventType]
    MODEL_CALL_STARTED: _ClassVar[EventType]
    MODEL_CALL_COMPLETED: _ClassVar[EventType]
    MODEL_CALL_FAILED: _ClassVar[EventType]
    TOOL_CALL_STARTED: _ClassVar[EventType]
    TOOL_CALL_COMPLETED: _ClassVar[EventType]
    TOOL_CALL_FAILED: _ClassVar[EventType]
    NODE_STARTED: _ClassVar[EventType]
    NODE_COMPLETED: _ClassVar[EventType]
    NODE_FAILED: _ClassVar[EventType]
    ROUTE_SELECTED: _ClassVar[EventType]
    OUTCOME_EVALUATED: _ClassVar[EventType]
    APPROVAL_REQUESTED: _ClassVar[EventType]
    APPROVAL_DECIDED: _ClassVar[EventType]
    ARTIFACT_PRODUCED: _ClassVar[EventType]
    EXPERIENCE_CANDIDATE_CREATED: _ClassVar[EventType]
    EXPERIENCE_REVISION_PUBLISHED: _ClassVar[EventType]
    EXPERIENCE_ACTIVATED: _ClassVar[EventType]
    EXPERIENCE_DEPRECATED: _ClassVar[EventType]
    EXPERIENCE_QUARANTINED: _ClassVar[EventType]
    EXPERIENCE_TOMBSTONED: _ClassVar[EventType]
    EXPERIENCE_EVALUATED: _ClassVar[EventType]
    EXPERIENCE_ADVISED: _ClassVar[EventType]
    EXPERIENCE_REPLAY_STARTED: _ClassVar[EventType]
    EXPERIENCE_REPLAY_COMPLETED: _ClassVar[EventType]
    MCP_SESSION_INITIALIZED: _ClassVar[EventType]
    MCP_CAPABILITY_SNAPSHOT: _ClassVar[EventType]
    MCP_RESOURCE_READ: _ClassVar[EventType]
    MCP_PROMPT_RENDERED: _ClassVar[EventType]
    EXPERIENCE_REPLAY_FAILED: _ClassVar[EventType]
    EXPERIENCE_IMPORTED: _ClassVar[EventType]
    EXPERIENCE_RULE_SELECTED: _ClassVar[EventType]
    EXPERIENCE_REJECTED_BY_BUDGET: _ClassVar[EventType]
    EXPERIENCE_BENEFIT_EVALUATED: _ClassVar[EventType]
    EXPERIENCE_APPLIED: _ClassVar[EventType]
    PACKAGE_INSPECTED: _ClassVar[EventType]
    PACKAGE_OPERATION_STARTED: _ClassVar[EventType]
    PACKAGE_MOUNTED: _ClassVar[EventType]
    PACKAGE_MOUNT_FAILED: _ClassVar[EventType]
    CAPABILITY_BOUND: _ClassVar[EventType]
    PACKAGE_VALIDATION_STARTED: _ClassVar[EventType]
    PACKAGE_VALIDATION_COMPLETED: _ClassVar[EventType]
    PACKAGE_UPGRADED: _ClassVar[EventType]
    PACKAGE_ROLLED_BACK: _ClassVar[EventType]
    PACKAGE_UNMOUNTED: _ClassVar[EventType]
    PACKAGE_OPERATION_COMMITTED: _ClassVar[EventType]

EVENT_TYPE_UNSPECIFIED: EventType
RUN_STARTED: EventType
RUN_COMPLETED: EventType
RUN_FAILED: EventType
RUN_CANCELLED: EventType
MODEL_CALL_STARTED: EventType
MODEL_CALL_COMPLETED: EventType
MODEL_CALL_FAILED: EventType
TOOL_CALL_STARTED: EventType
TOOL_CALL_COMPLETED: EventType
TOOL_CALL_FAILED: EventType
NODE_STARTED: EventType
NODE_COMPLETED: EventType
NODE_FAILED: EventType
ROUTE_SELECTED: EventType
OUTCOME_EVALUATED: EventType
APPROVAL_REQUESTED: EventType
APPROVAL_DECIDED: EventType
ARTIFACT_PRODUCED: EventType
EXPERIENCE_CANDIDATE_CREATED: EventType
EXPERIENCE_REVISION_PUBLISHED: EventType
EXPERIENCE_ACTIVATED: EventType
EXPERIENCE_DEPRECATED: EventType
EXPERIENCE_QUARANTINED: EventType
EXPERIENCE_TOMBSTONED: EventType
EXPERIENCE_EVALUATED: EventType
EXPERIENCE_ADVISED: EventType
EXPERIENCE_REPLAY_STARTED: EventType
EXPERIENCE_REPLAY_COMPLETED: EventType
MCP_SESSION_INITIALIZED: EventType
MCP_CAPABILITY_SNAPSHOT: EventType
MCP_RESOURCE_READ: EventType
MCP_PROMPT_RENDERED: EventType
EXPERIENCE_REPLAY_FAILED: EventType
EXPERIENCE_IMPORTED: EventType
EXPERIENCE_RULE_SELECTED: EventType
EXPERIENCE_REJECTED_BY_BUDGET: EventType
EXPERIENCE_BENEFIT_EVALUATED: EventType
EXPERIENCE_APPLIED: EventType
PACKAGE_INSPECTED: EventType
PACKAGE_OPERATION_STARTED: EventType
PACKAGE_MOUNTED: EventType
PACKAGE_MOUNT_FAILED: EventType
CAPABILITY_BOUND: EventType
PACKAGE_VALIDATION_STARTED: EventType
PACKAGE_VALIDATION_COMPLETED: EventType
PACKAGE_UPGRADED: EventType
PACKAGE_ROLLED_BACK: EventType
PACKAGE_UNMOUNTED: EventType
PACKAGE_OPERATION_COMMITTED: EventType

class EventEnvelope(_message.Message):
    __slots__ = (
        "event_id",
        "event_type",
        "schema_version",
        "timestamp",
        "repository_id",
        "run_id",
        "sequence_number",
        "correlation_id",
        "causation_id",
        "producer",
        "payload",
        "payload_hash",
        "signature",
        "attributes",
    )
    class AttributesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    REPOSITORY_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_NUMBER_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    CAUSATION_ID_FIELD_NUMBER: _ClassVar[int]
    PRODUCER_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_HASH_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    event_type: EventType
    schema_version: int
    timestamp: _timestamp_pb2.Timestamp
    repository_id: str
    run_id: str
    sequence_number: int
    correlation_id: str
    causation_id: str
    producer: str
    payload: _any_pb2.Any
    payload_hash: bytes
    signature: bytes
    attributes: _containers.ScalarMap[str, str]
    def __init__(
        self,
        event_id: _Optional[str] = ...,
        event_type: _Optional[_Union[EventType, str]] = ...,
        schema_version: _Optional[int] = ...,
        timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...,
        repository_id: _Optional[str] = ...,
        run_id: _Optional[str] = ...,
        sequence_number: _Optional[int] = ...,
        correlation_id: _Optional[str] = ...,
        causation_id: _Optional[str] = ...,
        producer: _Optional[str] = ...,
        payload: _Optional[_Union[_any_pb2.Any, _Mapping]] = ...,
        payload_hash: _Optional[bytes] = ...,
        signature: _Optional[bytes] = ...,
        attributes: _Optional[_Mapping[str, str]] = ...,
    ) -> None: ...
