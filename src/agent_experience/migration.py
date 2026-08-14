"""Safe, checksummed .exp package export and quarantined import."""

from __future__ import annotations

import hashlib
import time
import uuid
import warnings
import zipfile
from pathlib import Path

from google.protobuf import timestamp_pb2

from agent_experience.experience import ExperienceCatalog
from agent_experience.schema import events_pb2, experience_pb2, package_pb2
from agent_experience.storage import Repository

_MAX_FILE_SIZE = 16 * 1024 * 1024
_RECORDS = "records.bin"
_MANIFEST = "manifest.pb"


def export_package(repository: Repository, destination: Path, *, publisher: str = "") -> Path:
    warnings.warn(
        "export_package() writes legacy v1 packages; use ExperienceRuntime.export()",
        DeprecationWarning,
        stacklevel=2,
    )
    records = b"".join(
        len(raw).to_bytes(4, "big") + raw
        for raw in (
            value.SerializeToString(deterministic=True)
            for value in ExperienceCatalog(repository).definitions().values()
            if value.status in (experience_pb2.VALIDATED, experience_pb2.ACTIVE)
        )
    )
    now = timestamp_pb2.Timestamp()
    now.FromNanoseconds(time.time_ns())
    manifest = package_pb2.ExperiencePackageManifest(
        package_format_version=1,
        package_id=str(uuid.uuid4()),
        source_repository_id=repository.repository_id,
        exported_at=now,
        publisher=publisher,
        files=[
            package_pb2.PackageFile(
                path=_RECORDS, size=len(records), sha256=hashlib.sha256(records).digest()
            )
        ],
    )
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_MANIFEST, manifest.SerializeToString(deterministic=True))
        archive.writestr(_RECORDS, records)
    temporary.replace(destination)
    return destination


def import_package(repository: Repository, source: Path) -> int:
    warnings.warn(
        "import_package() is deprecated; use ExperienceRuntime.mount()",
        DeprecationWarning,
        stacklevel=2,
    )
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        if names != {_MANIFEST, _RECORDS}:
            raise ValueError("package contains unsupported or unsafe paths")
        for info in archive.infolist():
            if (
                info.file_size > _MAX_FILE_SIZE
                or info.filename.startswith(("/", "\\"))
                or ".." in Path(info.filename).parts
            ):
                raise ValueError("unsafe package member")
        manifest = package_pb2.ExperiencePackageManifest.FromString(archive.read(_MANIFEST))
        if manifest.package_format_version != 1:
            raise ValueError("unsupported package format")
        records = archive.read(_RECORDS)
        descriptor = next((item for item in manifest.files if item.path == _RECORDS), None)
        if (
            descriptor is None
            or descriptor.size != len(records)
            or descriptor.sha256 != hashlib.sha256(records).digest()
        ):
            raise ValueError("package checksum mismatch")
    known = {value.content_hash for value in ExperienceCatalog(repository).definitions().values()}
    offset = 0
    imported = 0
    while offset < len(records):
        if offset + 4 > len(records):
            raise ValueError("truncated package record")
        size = int.from_bytes(records[offset : offset + 4], "big")
        offset += 4
        if size > _MAX_FILE_SIZE or offset + size > len(records):
            raise ValueError("invalid package record size")
        definition = experience_pb2.ExperienceDefinition.FromString(records[offset : offset + size])
        offset += size
        if definition.content_hash in known:
            continue
        definition.status = experience_pb2.QUARANTINED
        definition.replay_allowed = False
        definition.exact_cache_allowed = False
        repository.append_event(
            events_pb2.EXPERIENCE_IMPORTED,
            run_id="",
            producer="package-import/v1",
            payload=definition,
            attributes={
                "source_repository_id": manifest.source_repository_id,
                "package_id": manifest.package_id,
            },
        )
        known.add(definition.content_hash)
        imported += 1
    return imported
