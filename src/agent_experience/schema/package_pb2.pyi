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
    def __init__(
        self, path: _Optional[str] = ..., size: _Optional[int] = ..., sha256: _Optional[bytes] = ...
    ) -> None: ...

class PackageCapability(_message.Message):
    __slots__ = (
        "capability_id",
        "version_constraint",
        "input_schema_hash",
        "output_schema_hash",
        "optional",
        "aliases",
    )
    CAPABILITY_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_CONSTRAINT_FIELD_NUMBER: _ClassVar[int]
    INPUT_SCHEMA_HASH_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_SCHEMA_HASH_FIELD_NUMBER: _ClassVar[int]
    OPTIONAL_FIELD_NUMBER: _ClassVar[int]
    ALIASES_FIELD_NUMBER: _ClassVar[int]
    capability_id: str
    version_constraint: str
    input_schema_hash: bytes
    output_schema_hash: bytes
    optional: bool
    aliases: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        capability_id: _Optional[str] = ...,
        version_constraint: _Optional[str] = ...,
        input_schema_hash: _Optional[bytes] = ...,
        output_schema_hash: _Optional[bytes] = ...,
        optional: _Optional[bool] = ...,
        aliases: _Optional[_Iterable[str]] = ...,
    ) -> None: ...

class ExperiencePackageManifest(_message.Message):
    __slots__ = (
        "package_format_version",
        "package_id",
        "source_repository_id",
        "exported_at",
        "publisher",
        "revision_ids",
        "files",
        "embedding_provider",
        "embedding_model",
        "embedding_dimension",
        "required_tool_contract_ids",
        "signature",
        "package_name",
        "package_version",
        "agent_experience_requires",
        "python_requires",
        "required_frameworks",
        "required_capabilities",
        "signature_algorithm",
        "signing_key_id",
        "signing_public_key",
        "package_digest",
        "supersedes_package_ids",
        "experience_schema_version",
    )
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
    PACKAGE_NAME_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_VERSION_FIELD_NUMBER: _ClassVar[int]
    AGENT_EXPERIENCE_REQUIRES_FIELD_NUMBER: _ClassVar[int]
    PYTHON_REQUIRES_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_FRAMEWORKS_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_ALGORITHM_FIELD_NUMBER: _ClassVar[int]
    SIGNING_KEY_ID_FIELD_NUMBER: _ClassVar[int]
    SIGNING_PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_DIGEST_FIELD_NUMBER: _ClassVar[int]
    SUPERSEDES_PACKAGE_IDS_FIELD_NUMBER: _ClassVar[int]
    EXPERIENCE_SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
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
    package_name: str
    package_version: str
    agent_experience_requires: str
    python_requires: str
    required_frameworks: _containers.RepeatedScalarFieldContainer[str]
    required_capabilities: _containers.RepeatedCompositeFieldContainer[PackageCapability]
    signature_algorithm: str
    signing_key_id: str
    signing_public_key: bytes
    package_digest: bytes
    supersedes_package_ids: _containers.RepeatedScalarFieldContainer[str]
    experience_schema_version: int
    def __init__(
        self,
        package_format_version: _Optional[int] = ...,
        package_id: _Optional[str] = ...,
        source_repository_id: _Optional[str] = ...,
        exported_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...,
        publisher: _Optional[str] = ...,
        revision_ids: _Optional[_Iterable[str]] = ...,
        files: _Optional[_Iterable[_Union[PackageFile, _Mapping]]] = ...,
        embedding_provider: _Optional[str] = ...,
        embedding_model: _Optional[str] = ...,
        embedding_dimension: _Optional[int] = ...,
        required_tool_contract_ids: _Optional[_Iterable[str]] = ...,
        signature: _Optional[bytes] = ...,
        package_name: _Optional[str] = ...,
        package_version: _Optional[str] = ...,
        agent_experience_requires: _Optional[str] = ...,
        python_requires: _Optional[str] = ...,
        required_frameworks: _Optional[_Iterable[str]] = ...,
        required_capabilities: _Optional[_Iterable[_Union[PackageCapability, _Mapping]]] = ...,
        signature_algorithm: _Optional[str] = ...,
        signing_key_id: _Optional[str] = ...,
        signing_public_key: _Optional[bytes] = ...,
        package_digest: _Optional[bytes] = ...,
        supersedes_package_ids: _Optional[_Iterable[str]] = ...,
        experience_schema_version: _Optional[int] = ...,
    ) -> None: ...
