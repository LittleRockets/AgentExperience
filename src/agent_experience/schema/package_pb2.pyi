import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PackageFile(_message.Message):
    __slots__ = ("path", "size", "sha256")
    PATH_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    path: str
    size: int
    sha256: bytes
    def __init__(self, path: _Optional[str] = ..., size: _Optional[int] = ..., sha256: _Optional[bytes] = ...) -> None: ...

class ExperiencePackageManifest(_message.Message):
    __slots__ = ("package_format_version", "package_id", "source_repository_id", "exported_at", "publisher", "revision_ids", "files", "embedding_provider", "embedding_model", "embedding_dimension", "required_tool_contract_ids", "signature")
    PACKAGE_FORMAT_VERSION_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_REPOSITORY_ID_FIELD_NUMBER: _ClassVar[int]
    EXPORTED_AT_FIELD_NUMBER: _ClassVar[int]
    PUBLISHER_FIELD_NUMBER: _ClassVar[int]
    REVISION_IDS_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_PROVIDER_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_MODEL_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_DIMENSION_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_TOOL_CONTRACT_IDS_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    package_format_version: int
    package_id: str
    source_repository_id: str
    exported_at: _timestamp_pb2.Timestamp
    publisher: str
    revision_ids: _containers.RepeatedScalarFieldContainer[str]
    files: _containers.RepeatedCompositeFieldContainer[PackageFile]
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    required_tool_contract_ids: _containers.RepeatedScalarFieldContainer[str]
    signature: bytes
    def __init__(self, package_format_version: _Optional[int] = ..., package_id: _Optional[str] = ..., source_repository_id: _Optional[str] = ..., exported_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., publisher: _Optional[str] = ..., revision_ids: _Optional[_Iterable[str]] = ..., files: _Optional[_Iterable[_Union[PackageFile, _Mapping]]] = ..., embedding_provider: _Optional[str] = ..., embedding_model: _Optional[str] = ..., embedding_dimension: _Optional[int] = ..., required_tool_contract_ids: _Optional[_Iterable[str]] = ..., signature: _Optional[bytes] = ...) -> None: ...
