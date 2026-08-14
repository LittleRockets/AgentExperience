from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TypedValue(_message.Message):
    __slots__ = (
        "string_value",
        "integer_value",
        "double_value",
        "boolean_value",
        "bytes_value",
        "list_value",
        "map_value",
        "reference",
        "null_value",
    )
    STRING_VALUE_FIELD_NUMBER: _ClassVar[int]
    INTEGER_VALUE_FIELD_NUMBER: _ClassVar[int]
    DOUBLE_VALUE_FIELD_NUMBER: _ClassVar[int]
    BOOLEAN_VALUE_FIELD_NUMBER: _ClassVar[int]
    BYTES_VALUE_FIELD_NUMBER: _ClassVar[int]
    LIST_VALUE_FIELD_NUMBER: _ClassVar[int]
    MAP_VALUE_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_FIELD_NUMBER: _ClassVar[int]
    NULL_VALUE_FIELD_NUMBER: _ClassVar[int]
    string_value: str
    integer_value: int
    double_value: float
    boolean_value: bool
    bytes_value: bytes
    list_value: ListValue
    map_value: MapValue
    reference: ValueReference
    null_value: bool
    def __init__(
        self,
        string_value: _Optional[str] = ...,
        integer_value: _Optional[int] = ...,
        double_value: _Optional[float] = ...,
        boolean_value: _Optional[bool] = ...,
        bytes_value: _Optional[bytes] = ...,
        list_value: _Optional[_Union[ListValue, _Mapping]] = ...,
        map_value: _Optional[_Union[MapValue, _Mapping]] = ...,
        reference: _Optional[_Union[ValueReference, _Mapping]] = ...,
        null_value: _Optional[bool] = ...,
    ) -> None: ...

class ListValue(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedCompositeFieldContainer[TypedValue]
    def __init__(
        self, values: _Optional[_Iterable[_Union[TypedValue, _Mapping]]] = ...
    ) -> None: ...

class MapValue(_message.Message):
    __slots__ = ("fields",)
    class FieldsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: TypedValue
        def __init__(
            self, key: _Optional[str] = ..., value: _Optional[_Union[TypedValue, _Mapping]] = ...
        ) -> None: ...

    FIELDS_FIELD_NUMBER: _ClassVar[int]
    fields: _containers.MessageMap[str, TypedValue]
    def __init__(self, fields: _Optional[_Mapping[str, TypedValue]] = ...) -> None: ...

class ValueReference(_message.Message):
    __slots__ = ("type", "path", "source_node_id")
    class ReferenceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        REFERENCE_TYPE_UNSPECIFIED: _ClassVar[ValueReference.ReferenceType]
        RUN_INPUT: _ClassVar[ValueReference.ReferenceType]
        NODE_OUTPUT: _ClassVar[ValueReference.ReferenceType]
        SECRET: _ClassVar[ValueReference.ReferenceType]
        ARTIFACT: _ClassVar[ValueReference.ReferenceType]

    REFERENCE_TYPE_UNSPECIFIED: ValueReference.ReferenceType
    RUN_INPUT: ValueReference.ReferenceType
    NODE_OUTPUT: ValueReference.ReferenceType
    SECRET: ValueReference.ReferenceType
    ARTIFACT: ValueReference.ReferenceType
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    SOURCE_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    type: ValueReference.ReferenceType
    path: str
    source_node_id: str
    def __init__(
        self,
        type: _Optional[_Union[ValueReference.ReferenceType, str]] = ...,
        path: _Optional[str] = ...,
        source_node_id: _Optional[str] = ...,
    ) -> None: ...
