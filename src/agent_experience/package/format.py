"""Deterministic, bounded v1/v2 `.exp` package encoding."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from google.protobuf import timestamp_pb2
from google.protobuf.json_format import MessageToJson
from packaging.version import InvalidVersion, Version

from agent_experience.schema import experience_pb2, package_pb2

from .model import CapabilityRequirement, MountPolicy, PackageInspection, ReasonCode, TrustStatus
from .signing import PackageSigner, TrustStore, verify_signature

_MANIFEST = "manifest.pb"
_RECORDS = "records.bin"
_ALLOWED = frozenset({_MANIFEST, _RECORDS})
_PACKAGE_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_SECRET = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s]{8,})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DecodedPackage:
    inspection: PackageInspection
    manifest: package_pb2.ExperiencePackageManifest
    definitions: tuple[experience_pb2.ExperienceDefinition, ...]


def write_package(
    destination: str | Path,
    definitions: Iterable[experience_pb2.ExperienceDefinition],
    *,
    package_name: str,
    package_version: str,
    source_repository_id: str,
    publisher: str = "",
    signer: PackageSigner | None = None,
    agent_experience_requires: str = ">=0.1.0,<1",
    python_requires: str = ">=3.10",
    required_frameworks: Iterable[str] = (),
) -> Path:
    if not _PACKAGE_NAME.fullmatch(package_name):
        raise ValueError("package name must be a normalized lowercase identifier")
    try:
        Version(package_version)
    except InvalidVersion as error:
        raise ValueError("package version must be a valid version") from error
    values = tuple(_exportable_definition(value) for value in definitions)
    records = _encode_records(values)
    now = timestamp_pb2.Timestamp()
    now.FromNanoseconds(time.time_ns())
    capabilities = _requirements(values)
    manifest = package_pb2.ExperiencePackageManifest(
        package_format_version=2,
        package_id=str(uuid.uuid4()),
        package_name=package_name,
        package_version=package_version,
        source_repository_id=source_repository_id,
        exported_at=now,
        publisher=publisher,
        revision_ids=[value.revision_id for value in values],
        files=[
            package_pb2.PackageFile(
                path=_RECORDS,
                size=len(records),
                sha256=hashlib.sha256(records).digest(),
            )
        ],
        agent_experience_requires=agent_experience_requires,
        python_requires=python_requires,
        required_frameworks=sorted(set(required_frameworks)),
        required_capabilities=[
            package_pb2.PackageCapability(
                capability_id=value.capability_id,
                version_constraint=value.version_constraint,
                input_schema_hash=bytes.fromhex(value.input_schema_hash),
                output_schema_hash=bytes.fromhex(value.output_schema_hash),
                optional=value.optional,
                aliases=value.aliases,
            )
            for value in capabilities
        ],
        required_tool_contract_ids=[value.capability_id for value in capabilities],
        experience_schema_version=max((value.schema_version for value in values), default=1),
    )
    if signer is not None:
        manifest.signature_algorithm = "Ed25519"
        manifest.signing_public_key = signer.public_key_bytes
        manifest.signing_key_id = signer.key_id
    manifest.package_digest = _content_digest(manifest, records)
    if signer is not None:
        manifest.signature = signer.sign(_signature_material(manifest, records))
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_suffix(destination_path.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_MANIFEST, manifest.SerializeToString(deterministic=True))
        archive.writestr(_RECORDS, records)
    temporary.replace(destination_path)
    return destination_path


def read_package(
    source: str | Path,
    *,
    policy: MountPolicy | None = None,
    trust_store: TrustStore | None = None,
) -> DecodedPackage:
    selected = policy or MountPolicy()
    path = Path(source)
    if path.stat().st_size > selected.maximum_package_bytes:
        raise ValueError("package exceeds configured size limit")
    with zipfile.ZipFile(path) as archive:
        _validate_archive(archive, selected)
        names = set(archive.namelist())
        if _MANIFEST not in names or _RECORDS not in names:
            raise ValueError("package is missing manifest or records")
        manifest = package_pb2.ExperiencePackageManifest.FromString(archive.read(_MANIFEST))
        if manifest.package_format_version not in (1, 2):
            raise ValueError("unsupported package format")
        if manifest.package_format_version == 1 and not selected.allow_legacy_v1:
            raise ValueError("legacy v1 package is disabled by policy")
        if manifest.package_format_version == 2:
            if not _PACKAGE_NAME.fullmatch(manifest.package_name):
                raise ValueError("package manifest has an invalid name")
            try:
                Version(manifest.package_version)
            except InvalidVersion as error:
                raise ValueError("package manifest has an invalid version") from error
        records = archive.read(_RECORDS)
    descriptor = next((value for value in manifest.files if value.path == _RECORDS), None)
    if (
        descriptor is None
        or descriptor.size != len(records)
        or descriptor.sha256 != hashlib.sha256(records).digest()
    ):
        raise ValueError("package checksum mismatch")
    definitions = _decode_records(records, selected.maximum_uncompressed_bytes)
    if manifest.package_format_version == 2:
        expected_digest = _content_digest(manifest, records)
        if not manifest.package_digest or manifest.package_digest != expected_digest:
            raise ValueError("package digest mismatch")
        trust, reason = _verify_trust(manifest, records, trust_store)
    else:
        trust, reason = TrustStatus.LEGACY_UNSIGNED, ReasonCode.LEGACY_UNSIGNED
    if trust == TrustStatus.SIGNATURE_INVALID:
        raise ValueError("package signature is invalid")
    if selected.require_trusted_signature and trust != TrustStatus.SIGNED_TRUSTED:
        raise PermissionError("package is not signed by a trusted key")
    if not selected.allow_unsigned and trust in (
        TrustStatus.UNSIGNED,
        TrustStatus.LEGACY_UNSIGNED,
    ):
        raise PermissionError("unsigned packages are disabled by policy")
    requirements = tuple(
        CapabilityRequirement(
            value.capability_id,
            value.version_constraint,
            value.input_schema_hash.hex(),
            value.output_schema_hash.hex(),
            value.optional,
            tuple(value.aliases),
        )
        for value in manifest.required_capabilities
    )
    if not requirements and manifest.required_tool_contract_ids:
        requirements = tuple(
            CapabilityRequirement(value) for value in manifest.required_tool_contract_ids
        )
    inspection = PackageInspection(
        package_id=manifest.package_id,
        package_name=manifest.package_name or manifest.package_id,
        package_version=manifest.package_version or "0.0.0-legacy",
        package_digest=(manifest.package_digest or hashlib.sha256(records).digest()).hex(),
        publisher=manifest.publisher,
        format_version=manifest.package_format_version,
        revision_ids=tuple(manifest.revision_ids),
        requirements=requirements,
        required_frameworks=tuple(manifest.required_frameworks),
        trust=trust,
        reason=reason,
        source=str(path),
        legacy=manifest.package_format_version == 1,
    )
    return DecodedPackage(inspection, manifest, definitions)


def _validate_archive(archive: zipfile.ZipFile, policy: MountPolicy) -> None:
    names = archive.namelist()
    if len(names) != len(set(names)) or not set(names).issubset(_ALLOWED):
        raise ValueError("package contains unsupported, duplicate, or unsafe paths")
    total = 0
    for info in archive.infolist():
        parts = Path(info.filename).parts
        if info.filename.startswith(("/", "\\")) or ".." in parts or info.is_dir():
            raise ValueError("unsafe package member")
        total += info.file_size
        if info.file_size > policy.maximum_uncompressed_bytes:
            raise ValueError("package member exceeds configured size limit")
        if (
            info.compress_size
            and info.file_size / info.compress_size > policy.maximum_compression_ratio
        ):
            raise ValueError("package compression ratio exceeds configured limit")
    if total > policy.maximum_uncompressed_bytes:
        raise ValueError("package uncompressed size exceeds configured limit")


def _encode_records(values: Iterable[experience_pb2.ExperienceDefinition]) -> bytes:
    result = bytearray()
    for value in values:
        raw = value.SerializeToString(deterministic=True)
        result.extend(len(raw).to_bytes(4, "big"))
        result.extend(raw)
    return bytes(result)


def _decode_records(
    records: bytes, maximum_size: int
) -> tuple[experience_pb2.ExperienceDefinition, ...]:
    offset = 0
    values: list[experience_pb2.ExperienceDefinition] = []
    while offset < len(records):
        if offset + 4 > len(records):
            raise ValueError("truncated package record")
        size = int.from_bytes(records[offset : offset + 4], "big")
        offset += 4
        if size > maximum_size or offset + size > len(records):
            raise ValueError("invalid package record size")
        values.append(
            experience_pb2.ExperienceDefinition.FromString(records[offset : offset + size])
        )
        offset += size
    return tuple(values)


def _copy_definition(
    value: experience_pb2.ExperienceDefinition,
) -> experience_pb2.ExperienceDefinition:
    copied = experience_pb2.ExperienceDefinition()
    copied.CopyFrom(value)
    return copied


def _exportable_definition(
    value: experience_pb2.ExperienceDefinition,
) -> experience_pb2.ExperienceDefinition:
    copied = _copy_definition(value)
    copied.source_run_ids.clear()
    copied.created_by = ""
    for rule in copied.delta.rules:
        rule.evidence_run_ids.clear()
    rendered = MessageToJson(copied, preserving_proto_field_name=True)
    if _SECRET.search(rendered):
        raise ValueError("experience contains content that resembles a secret")
    return copied


def _requirements(
    definitions: Iterable[experience_pb2.ExperienceDefinition],
) -> tuple[CapabilityRequirement, ...]:
    values: dict[str, CapabilityRequirement] = {}
    for definition in definitions:
        tools = [*definition.applicability.required_tools]
        tools.extend(node.tool for node in definition.strategy.nodes if node.tool.contract_id)
        for tool in tools:
            if not tool.contract_id:
                continue
            portable_id = _portable_capability_id(tool.contract_id, tool.name)
            values[portable_id] = CapabilityRequirement(
                portable_id,
                tool.version_constraint,
                tool.input_schema_hash.hex(),
                tool.output_schema_hash.hex(),
                aliases=(tool.contract_id,) if portable_id != tool.contract_id else (),
            )
    return tuple(values[key] for key in sorted(values))


def _portable_capability_id(contract_id: str, name: str) -> str:
    if contract_id.startswith("capability://"):
        return contract_id
    display = name
    if not display and contract_id.startswith("python://"):
        display = contract_id.rsplit(".", 1)[-1].split("@", 1)[0]
    if not display:
        return contract_id
    slug = re.sub(r"[^a-z0-9]+", "-", display.lower()).strip("-")
    return f"capability://{slug}@1"


def _canonical_manifest(
    manifest: package_pb2.ExperiencePackageManifest, *, clear_digest: bool
) -> bytes:
    value = package_pb2.ExperiencePackageManifest()
    value.CopyFrom(manifest)
    value.signature = b""
    if clear_digest:
        value.package_digest = b""
    return value.SerializeToString(deterministic=True)


def _content_digest(manifest: package_pb2.ExperiencePackageManifest, records: bytes) -> bytes:
    return hashlib.sha256(_canonical_manifest(manifest, clear_digest=True) + records).digest()


def _signature_material(manifest: package_pb2.ExperiencePackageManifest, records: bytes) -> bytes:
    return _canonical_manifest(manifest, clear_digest=False) + records


def _verify_trust(
    manifest: package_pb2.ExperiencePackageManifest,
    records: bytes,
    trust_store: TrustStore | None,
) -> tuple[TrustStatus, ReasonCode]:
    if not manifest.signature:
        return TrustStatus.UNSIGNED, ReasonCode.UNSIGNED
    if manifest.signature_algorithm != "Ed25519" or not manifest.signing_public_key:
        return TrustStatus.SIGNATURE_INVALID, ReasonCode.SIGNATURE_INVALID
    if not verify_signature(
        manifest.signing_public_key,
        manifest.signature,
        _signature_material(manifest, records),
    ):
        return TrustStatus.SIGNATURE_INVALID, ReasonCode.SIGNATURE_INVALID
    if trust_store and trust_store.is_trusted(manifest.signing_key_id, manifest.signing_public_key):
        return TrustStatus.SIGNED_TRUSTED, ReasonCode.SIGNED_TRUSTED
    return TrustStatus.SIGNED_UNKNOWN, ReasonCode.SIGNED_UNKNOWN
