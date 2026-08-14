"""Public, immutable package inspection and mount results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ReasonCode(str, Enum):
    OK = "ok"
    DUPLICATE = "duplicate"
    LEGACY_UNSIGNED = "legacy_unsigned"
    UNSIGNED = "unsigned"
    SIGNED_UNKNOWN = "signed_unknown"
    SIGNED_TRUSTED = "signed_trusted"
    SIGNATURE_INVALID = "signature_invalid"
    FORMAT_UNSUPPORTED = "format_unsupported"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    PACKAGE_CONFLICT = "package_conflict"
    VERSION_INCOMPATIBLE = "version_incompatible"
    FRAMEWORK_MISSING = "framework_missing"
    CAPABILITY_MISSING = "capability_missing"
    CAPABILITY_AMBIGUOUS = "capability_ambiguous"
    SCHEMA_INCOMPATIBLE = "schema_incompatible"
    LOCAL_VALIDATION_REQUIRED = "local_validation_required"
    LOCAL_VALIDATION_FAILED = "local_validation_failed"
    SECURITY_REJECTED = "security_rejected"
    SOURCE_UNAVAILABLE = "source_unavailable"
    CACHE_MISS = "cache_miss"
    OPERATION_CONFLICT = "operation_conflict"


class CompatibilityStatus(str, Enum):
    COMPATIBLE = "compatible"
    COMPATIBLE_WITH_BINDING = "compatible_with_binding"
    NEEDS_BINDING = "needs_binding"
    NEEDS_LOCAL_VALIDATION = "needs_local_validation"
    INCOMPATIBLE = "incompatible"
    REJECTED_SECURITY = "rejected_security"


class TrustStatus(str, Enum):
    UNSIGNED = "unsigned"
    LEGACY_UNSIGNED = "legacy_unsigned"
    SIGNED_UNKNOWN = "signed_unknown"
    SIGNED_TRUSTED = "signed_trusted"
    SIGNATURE_INVALID = "signature_invalid"


class MountStatus(str, Enum):
    INSPECTED = "inspected"
    MOUNTED_IN_QUARANTINE = "mounted_in_quarantine"
    VALIDATED = "validated"
    ACTIVE = "active"
    REJECTED = "rejected"
    UNMOUNTED = "unmounted"


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    capability_id: str
    version_constraint: str = ""
    input_schema_hash: str = ""
    output_schema_hash: str = ""
    optional: bool = False
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    required: str
    local: str = ""
    status: CompatibilityStatus = CompatibilityStatus.NEEDS_BINDING
    reason: ReasonCode = ReasonCode.CAPABILITY_MISSING


@dataclass(frozen=True, slots=True)
class PackageInspection:
    package_id: str
    package_name: str
    package_version: str
    package_digest: str
    publisher: str
    format_version: int
    revision_ids: tuple[str, ...]
    requirements: tuple[CapabilityRequirement, ...]
    required_frameworks: tuple[str, ...]
    trust: TrustStatus
    reason: ReasonCode
    source: str
    legacy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MountReport:
    package_id: str
    package_name: str
    package_version: str
    package_digest: str
    publisher: str
    trust: TrustStatus
    status: MountStatus
    reason: ReasonCode
    imported: int = 0
    compatible: int = 0
    needs_binding: int = 0
    incompatible: int = 0
    duplicate: int = 0
    active: int = 0
    bindings: tuple[CapabilityBinding, ...] = ()
    messages: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"{self.package_name}@{self.package_version}: {self.status.value}; "
            f"imported={self.imported}, compatible={self.compatible}, "
            f"needs_binding={self.needs_binding}, incompatible={self.incompatible}, "
            f"duplicate={self.duplicate}, trust={self.trust.value}"
        )


@dataclass(frozen=True, slots=True)
class MountPolicy:
    require_trusted_signature: bool = False
    allow_unsigned: bool = True
    allow_legacy_v1: bool = True
    offline: bool = False
    maximum_package_bytes: int = 16 * 1024 * 1024
    maximum_uncompressed_bytes: int = 32 * 1024 * 1024
    maximum_compression_ratio: int = 100
    network_timeout_seconds: float = 15.0
    maximum_redirects: int = 3
    automatic_activation: bool = False
