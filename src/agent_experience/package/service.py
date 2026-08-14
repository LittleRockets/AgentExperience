"""High-level inspect, mount, validate, upgrade, rollback and unmount service."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from agent_experience.events.factory import unpack_payload
from agent_experience.experience import ExperienceCatalog
from agent_experience.schema import events_pb2, experience_pb2
from agent_experience.storage import Repository

from .capability import CapabilityCatalog
from .compatibility import CompatibilityReport, resolve_compatibility
from .format import DecodedPackage, read_package, write_package
from .model import (
    CompatibilityStatus,
    MountPolicy,
    MountReport,
    MountStatus,
    PackageInspection,
    ReasonCode,
)
from .signing import PackageSigner, TrustStore
from .source import DefaultPackageSource, PackageSource


class PackageService:
    def __init__(
        self,
        repository: Repository,
        *,
        capabilities: CapabilityCatalog | None = None,
        frameworks: frozenset[str] = frozenset(),
        policy: MountPolicy | None = None,
        source: PackageSource | None = None,
    ) -> None:
        self.repository = repository
        self.capabilities = capabilities or CapabilityCatalog()
        self.frameworks = frameworks
        self.policy = policy or MountPolicy()
        self.trust_store = TrustStore(repository.path / ".experience-trust" / "trusted-keys.json")
        self.source = source or DefaultPackageSource(repository.path / "packages" / "cache")

    def inspect(self, reference: str | os.PathLike[str], *, sha256: str = "") -> PackageInspection:
        decoded, _ = self._decode(reference, sha256=sha256)
        return decoded.inspection

    def mount(
        self,
        reference: str | os.PathLike[str],
        *,
        sha256: str = "",
        bindings: dict[str, str] | None = None,
    ) -> MountReport:
        operation_id = str(uuid.uuid4())
        with self._operation_lock(operation_id):
            decoded, compatibility = self._decode(reference, sha256=sha256)
            previous = next(
                (
                    value
                    for value in reversed(self._report_history())
                    if value.package_name == decoded.inspection.package_name
                    and value.package_version == decoded.inspection.package_version
                    and value.status != MountStatus.UNMOUNTED
                ),
                None,
            )
            if previous and previous.package_digest == decoded.inspection.package_digest:
                return replace(
                    previous,
                    reason=ReasonCode.DUPLICATE,
                    duplicate=len(decoded.definitions),
                )
            if previous:
                raise ValueError("same package name/version has a different digest")
            self._append_operation(events_pb2.PACKAGE_OPERATION_STARTED, operation_id, decoded)
            try:
                report = self._mount_decoded(decoded, compatibility, bindings or {})
                self.repository.append_event(
                    events_pb2.PACKAGE_MOUNTED,
                    run_id="",
                    producer="package-service/v2",
                    payload=_report_payload(report),
                    attributes=_package_attributes(decoded, operation_id),
                )
                self._append_operation(
                    events_pb2.PACKAGE_OPERATION_COMMITTED, operation_id, decoded
                )
                return report
            except BaseException as error:
                self.repository.append_event(
                    events_pb2.PACKAGE_MOUNT_FAILED,
                    run_id="",
                    producer="package-service/v2",
                    payload={"operation_id": operation_id, "error_type": type(error).__name__},
                    attributes=_package_attributes(decoded, operation_id),
                )
                raise

    def mounts(self) -> tuple[MountReport, ...]:
        values = self._current_reports()
        return tuple(values[key] for key in sorted(values))

    def validate_mount(
        self,
        package_name: str,
        verifier: Callable[[experience_pb2.ExperienceDefinition], bool],
        *,
        max_runs: int = 6,
    ) -> MountReport:
        if max_runs <= 0:
            raise ValueError("max_runs must be positive")
        current = self._find_by_name(package_name)
        package_id = current.package_id
        self.repository.append_event(
            events_pb2.PACKAGE_VALIDATION_STARTED,
            run_id="",
            producer="package-service/v2",
            payload={"package_id": package_id, "maximum_runs": max_runs},
        )
        validated = 0
        failed = 0
        for definition in self._package_definitions(package_id)[:max_runs]:
            if bool(verifier(definition)):
                revision = _revision(definition, experience_pb2.VALIDATED)
                self.repository.append_event(
                    events_pb2.EXPERIENCE_REVISION_PUBLISHED,
                    run_id="",
                    producer="package-local-validation/v1",
                    payload=revision,
                    attributes={"package_id": package_id, "local_validation": "passed"},
                )
                validated += 1
            else:
                failed += 1
        status = MountStatus.VALIDATED if validated and not failed else MountStatus.REJECTED
        reason = (
            ReasonCode.OK if status == MountStatus.VALIDATED else ReasonCode.LOCAL_VALIDATION_FAILED
        )
        report = replace(
            current,
            status=status,
            reason=reason,
            compatible=validated,
            incompatible=current.incompatible + failed,
        )
        self.repository.append_event(
            events_pb2.PACKAGE_VALIDATION_COMPLETED,
            run_id="",
            producer="package-service/v2",
            payload=_report_payload(report),
            attributes={"package_id": package_id},
        )
        return report

    def upgrade(
        self,
        package_name: str,
        reference: str | os.PathLike[str],
        *,
        sha256: str = "",
    ) -> MountReport:
        previous = self._find_by_name(package_name)
        report = self.mount(reference, sha256=sha256)
        if report.package_name != package_name:
            self.unmount(report.package_name)
            raise ValueError("upgrade package name does not match the mounted package")
        self.repository.append_event(
            events_pb2.PACKAGE_UPGRADED,
            run_id="",
            producer="package-service/v2",
            payload={
                "package_name": package_name,
                "from_package_id": previous.package_id,
                "to_package_id": report.package_id,
            },
            attributes={"package_id": report.package_id},
        )
        return report

    def rollback(self, package_name: str) -> MountReport:
        history = [
            value
            for value in self._report_history()
            if value.package_name == package_name and value.status != MountStatus.UNMOUNTED
        ]
        generations: list[MountReport] = []
        for value in history:
            if not generations or generations[-1].package_id != value.package_id:
                generations.append(value)
            else:
                generations[-1] = value
        if len(generations) < 2:
            raise ValueError("package has no previous mounted generation")
        current, previous = generations[-1], generations[-2]
        self.repository.append_event(
            events_pb2.PACKAGE_ROLLED_BACK,
            run_id="",
            producer="package-service/v2",
            payload=_report_payload(previous),
            attributes={
                "package_id": previous.package_id,
                "replaced_package_id": current.package_id,
            },
        )
        return previous

    def unmount(self, package_name: str) -> MountReport:
        current = self._find_by_name(package_name)
        for definition in self._package_definitions(current.package_id):
            tombstone = _revision(definition, experience_pb2.TOMBSTONED)
            self.repository.append_event(
                events_pb2.EXPERIENCE_TOMBSTONED,
                run_id="",
                producer="package-service/v2",
                payload=tombstone,
                attributes={"package_id": current.package_id},
            )
        report = replace(current, status=MountStatus.UNMOUNTED, active=0)
        self.repository.append_event(
            events_pb2.PACKAGE_UNMOUNTED,
            run_id="",
            producer="package-service/v2",
            payload=_report_payload(report),
            attributes={"package_id": current.package_id},
        )
        return report

    def export(
        self,
        destination: str | Path,
        *,
        name: str,
        version: str,
        publisher: str = "",
        signer: PackageSigner | None = None,
    ) -> Path:
        definitions = tuple(
            value
            for value in ExperienceCatalog(self.repository).definitions().values()
            if value.status in (experience_pb2.VALIDATED, experience_pb2.ACTIVE)
        )
        return write_package(
            destination,
            definitions,
            package_name=name,
            package_version=version,
            source_repository_id=self.repository.repository_id,
            publisher=publisher,
            signer=signer,
        )

    def _decode(
        self, reference: str | os.PathLike[str], *, sha256: str
    ) -> tuple[DecodedPackage, CompatibilityReport]:
        resolved = self.source.resolve(reference, policy=self.policy, expected_sha256=sha256)
        decoded = read_package(resolved.path, policy=self.policy, trust_store=self.trust_store)
        inspection = replace(decoded.inspection, source=resolved.source)
        decoded = DecodedPackage(inspection, decoded.manifest, decoded.definitions)
        compatibility = resolve_compatibility(
            inspection,
            agent_requires=decoded.manifest.agent_experience_requires,
            python_requires=decoded.manifest.python_requires,
            catalog=self.capabilities,
            frameworks=self.frameworks,
        )
        return decoded, compatibility

    def _mount_decoded(
        self,
        decoded: DecodedPackage,
        compatibility: CompatibilityReport,
        explicit_bindings: dict[str, str],
    ) -> MountReport:
        bindings = list(compatibility.bindings)
        if explicit_bindings:
            unknown = [
                value
                for value in explicit_bindings.values()
                if self.capabilities.implementation(value) is None
            ]
            if unknown:
                raise ValueError("explicit binding targets are not registered local capabilities")
            bindings = [
                type(value)(
                    value.required,
                    explicit_bindings.get(value.required, value.local),
                    CompatibilityStatus.COMPATIBLE_WITH_BINDING
                    if value.required in explicit_bindings
                    else value.status,
                    ReasonCode.OK if value.required in explicit_bindings else value.reason,
                )
                for value in bindings
            ]
        unresolved = [
            value for value in bindings if value.status == CompatibilityStatus.NEEDS_BINDING
        ]
        known_hashes = {
            value.content_hash
            for value in ExperienceCatalog(self.repository).definitions().values()
        }
        imported = 0
        duplicate = 0
        for definition in decoded.definitions:
            if definition.content_hash in known_hashes:
                duplicate += 1
                continue
            imported_value = _imported_definition(definition, decoded.inspection.package_id)
            self.repository.append_event(
                events_pb2.EXPERIENCE_IMPORTED,
                run_id="",
                producer="package-service/v2",
                payload=imported_value,
                attributes={
                    "package_id": decoded.inspection.package_id,
                    "package_name": decoded.inspection.package_name,
                    "source_revision_id": definition.revision_id,
                },
            )
            known_hashes.add(definition.content_hash)
            imported += 1
        for value in bindings:
            if value.local:
                self.repository.append_event(
                    events_pb2.CAPABILITY_BOUND,
                    run_id="",
                    producer="package-service/v2",
                    payload={
                        "package_id": decoded.inspection.package_id,
                        "required": value.required,
                        "local": value.local,
                    },
                )
        unresolved_ids = {value.required for value in unresolved}
        requirement_by_contract = {
            alias: requirement.capability_id
            for requirement in decoded.inspection.requirements
            for alias in (requirement.capability_id, *requirement.aliases)
        }
        compatible = 0
        if compatibility.status != CompatibilityStatus.INCOMPATIBLE:
            for definition in decoded.definitions:
                contracts = {
                    tool.contract_id
                    for tool in definition.applicability.required_tools
                    if tool.contract_id
                }
                contracts.update(
                    node.tool.contract_id
                    for node in definition.strategy.nodes
                    if node.tool.contract_id
                )
                required = {requirement_by_contract.get(value, value) for value in contracts}
                if not required.intersection(unresolved_ids):
                    compatible += 1
        compatible = min(compatible, imported)
        incompatible = imported - compatible
        status = MountStatus.MOUNTED_IN_QUARANTINE
        reason = ReasonCode.LOCAL_VALIDATION_REQUIRED if compatible else compatibility.reason
        return MountReport(
            decoded.inspection.package_id,
            decoded.inspection.package_name,
            decoded.inspection.package_version,
            decoded.inspection.package_digest,
            decoded.inspection.publisher,
            decoded.inspection.trust,
            status,
            reason,
            imported=imported,
            compatible=compatible,
            needs_binding=len(unresolved),
            incompatible=incompatible,
            duplicate=duplicate,
            bindings=tuple(bindings),
            messages=compatibility.messages,
        )

    def _current_reports(self) -> dict[str, MountReport]:
        values: dict[str, MountReport] = {}
        for report in self._report_history():
            key = report.package_name
            if report.status == MountStatus.UNMOUNTED:
                values.pop(key, None)
            else:
                values[key] = report
        return values

    def _report_history(self) -> list[MountReport]:
        types = {
            events_pb2.PACKAGE_MOUNTED,
            events_pb2.PACKAGE_VALIDATION_COMPLETED,
            events_pb2.PACKAGE_ROLLED_BACK,
            events_pb2.PACKAGE_UNMOUNTED,
        }
        result: list[MountReport] = []
        for event in self.repository.events():
            if event.event_type in types:
                result.append(_report_from_payload(unpack_payload(event)))
        return result

    def _find_by_name(self, package_name: str) -> MountReport:
        values = [value for value in self.mounts() if value.package_name == package_name]
        if not values:
            raise KeyError(package_name)
        return values[-1]

    def _package_definitions(
        self, package_id: str
    ) -> tuple[experience_pb2.ExperienceDefinition, ...]:
        values: list[experience_pb2.ExperienceDefinition] = []
        for event in self.repository.events():
            if (
                event.event_type == events_pb2.EXPERIENCE_IMPORTED
                and event.attributes.get("package_id") == package_id
            ):
                value = experience_pb2.ExperienceDefinition()
                if event.payload.Unpack(value):
                    values.append(value)
        return tuple(values)

    def _append_operation(
        self, event_type: int, operation_id: str, decoded: DecodedPackage
    ) -> None:
        self.repository.append_event(
            event_type,
            run_id="",
            producer="package-service/v2",
            payload={"operation_id": operation_id},
            attributes=_package_attributes(decoded, operation_id),
        )

    @contextmanager
    def _operation_lock(self, operation_id: str) -> Iterator[None]:
        path = self.repository.path / "packages" / "mount.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            if time.time() - path.stat().st_mtime > 300:
                path.unlink()
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            else:
                raise RuntimeError("another package operation is in progress") from error
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(f"{os.getpid()} {operation_id}\n")
            yield
        finally:
            path.unlink(missing_ok=True)


def _imported_definition(
    definition: experience_pb2.ExperienceDefinition, package_id: str
) -> experience_pb2.ExperienceDefinition:
    value = experience_pb2.ExperienceDefinition()
    value.CopyFrom(definition)
    value.parent_revision_ids.append(definition.revision_id)
    value.experience_id = str(uuid.uuid5(uuid.UUID(package_id), definition.experience_id))
    value.revision_id = str(uuid.uuid5(uuid.UUID(package_id), definition.revision_id))
    value.generation += 1
    value.status = experience_pb2.QUARANTINED
    value.replay_allowed = False
    value.exact_cache_allowed = False
    return value


def _revision(
    definition: experience_pb2.ExperienceDefinition, status: int
) -> experience_pb2.ExperienceDefinition:
    value = experience_pb2.ExperienceDefinition()
    value.CopyFrom(definition)
    value.parent_revision_ids.append(definition.revision_id)
    value.revision_id = str(uuid.uuid4())
    value.generation += 1
    value.status = cast(Any, status)
    value.replay_allowed = False
    value.exact_cache_allowed = False
    return value


def _package_attributes(decoded: DecodedPackage, operation_id: str) -> dict[str, str]:
    return {
        "package_id": decoded.inspection.package_id,
        "package_name": decoded.inspection.package_name,
        "package_version": decoded.inspection.package_version,
        "package_digest": decoded.inspection.package_digest,
        "operation_id": operation_id,
    }


def _report_payload(report: MountReport) -> dict[str, Any]:
    return {
        "package_id": report.package_id,
        "package_name": report.package_name,
        "package_version": report.package_version,
        "package_digest": report.package_digest,
        "publisher": report.publisher,
        "trust": report.trust.value,
        "status": report.status.value,
        "reason": report.reason.value,
        "imported": report.imported,
        "compatible": report.compatible,
        "needs_binding": report.needs_binding,
        "incompatible": report.incompatible,
        "duplicate": report.duplicate,
        "active": report.active,
        "bindings": [
            {
                "required": value.required,
                "local": value.local,
                "status": value.status.value,
                "reason": value.reason.value,
            }
            for value in report.bindings
        ],
        "messages": list(report.messages),
    }


def _report_from_payload(payload: dict[str, Any]) -> MountReport:
    from .model import CapabilityBinding, TrustStatus

    return MountReport(
        package_id=str(payload.get("package_id", "")),
        package_name=str(payload.get("package_name", "")),
        package_version=str(payload.get("package_version", "")),
        package_digest=str(payload.get("package_digest", "")),
        publisher=str(payload.get("publisher", "")),
        trust=TrustStatus(str(payload.get("trust", TrustStatus.UNSIGNED.value))),
        status=MountStatus(str(payload.get("status", MountStatus.INSPECTED.value))),
        reason=ReasonCode(str(payload.get("reason", ReasonCode.OK.value))),
        imported=int(payload.get("imported", 0)),
        compatible=int(payload.get("compatible", 0)),
        needs_binding=int(payload.get("needs_binding", 0)),
        incompatible=int(payload.get("incompatible", 0)),
        duplicate=int(payload.get("duplicate", 0)),
        active=int(payload.get("active", 0)),
        bindings=tuple(
            CapabilityBinding(
                str(value.get("required", "")),
                str(value.get("local", "")),
                CompatibilityStatus(str(value.get("status"))),
                ReasonCode(str(value.get("reason"))),
            )
            for value in payload.get("bindings", [])
        ),
        messages=tuple(str(value) for value in payload.get("messages", [])),
    )
