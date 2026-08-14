"""Minimal command-line entry point for the pre-alpha package."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from agent_experience import __version__
from agent_experience.events.factory import unpack_payload
from agent_experience.experience import CandidateService
from agent_experience.migration import export_package, import_package
from agent_experience.package import PackageService, PackageSigner, load_public_key
from agent_experience.schema import events_pb2
from agent_experience.storage.repository import Repository


def main(argv: Sequence[str] | None = None) -> int:
    """Run the AgentExperience CLI."""

    parser = argparse.ArgumentParser(prog="agent-exp")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    inspect_parser = subparsers.add_parser("inspect", help="print repository events as JSON lines")
    inspect_parser.add_argument("repository", type=Path)
    verify_parser = subparsers.add_parser("verify", help="verify repository integrity")
    verify_parser.add_argument("repository", type=Path)
    extract_parser = subparsers.add_parser(
        "extract", help="create deduplicated candidate experiences"
    )
    extract_parser.add_argument("repository", type=Path)
    extract_parser.add_argument("--minimum-confidence", type=float, default=0.8)
    candidates_parser = subparsers.add_parser("candidates", help="print candidate experiences")
    candidates_parser.add_argument("repository", type=Path)
    export_parser = subparsers.add_parser("export", help="export validated experiences")
    export_parser.add_argument("repository", type=Path)
    export_parser.add_argument("destination", type=Path)
    export_parser.add_argument("--publisher", default="")
    import_parser = subparsers.add_parser("import", help="safely import quarantined experiences")
    import_parser.add_argument("repository", type=Path)
    import_parser.add_argument("source", type=Path)
    benefits_parser = subparsers.add_parser("benefits", help="print measured experience benefits")
    benefits_parser.add_argument("repository", type=Path)
    benefits_parser.add_argument("--experience-id", default="")
    package_parser = subparsers.add_parser("package", help="inspect and manage portable packages")
    package_commands = package_parser.add_subparsers(dest="package_command", required=True)
    package_inspect = package_commands.add_parser("inspect", help="inspect without mounting")
    package_inspect.add_argument("repository", type=Path)
    package_inspect.add_argument("source")
    package_inspect.add_argument("--sha256", default="")
    package_verify = package_commands.add_parser(
        "verify", help="verify package integrity/signature"
    )
    package_verify.add_argument("repository", type=Path)
    package_verify.add_argument("source")
    package_verify.add_argument("--sha256", default="")
    package_mount = package_commands.add_parser("mount", help="mount safely in quarantine")
    package_mount.add_argument("repository", type=Path)
    package_mount.add_argument("source")
    package_mount.add_argument("--sha256", default="")
    package_list = package_commands.add_parser("list", help="list mounted packages")
    package_list.add_argument("repository", type=Path)
    package_export = package_commands.add_parser("export", help="export a v2 package")
    package_export.add_argument("repository", type=Path)
    package_export.add_argument("destination", type=Path)
    package_export.add_argument("--name", required=True)
    package_export.add_argument("--package-version", required=True)
    package_export.add_argument("--publisher", default="")
    package_export.add_argument("--signing-key", type=Path)
    package_upgrade = package_commands.add_parser("upgrade", help="mount a newer generation")
    package_upgrade.add_argument("repository", type=Path)
    package_upgrade.add_argument("name")
    package_upgrade.add_argument("source")
    package_upgrade.add_argument("--sha256", default="")
    package_rollback = package_commands.add_parser("rollback", help="restore previous generation")
    package_rollback.add_argument("repository", type=Path)
    package_rollback.add_argument("name")
    package_unmount = package_commands.add_parser("unmount", help="disable a mounted package")
    package_unmount.add_argument("repository", type=Path)
    package_unmount.add_argument("name")
    trust_parser = subparsers.add_parser("trust", help="manage trusted package signing keys")
    trust_commands = trust_parser.add_subparsers(dest="trust_command", required=True)
    trust_add = trust_commands.add_parser("add", help="trust an Ed25519 public key")
    trust_add.add_argument("repository", type=Path)
    trust_add.add_argument("public_key", type=Path)
    trust_add.add_argument("--alias", default="")
    trust_list = trust_commands.add_parser("list", help="list trusted keys")
    trust_list.add_argument("repository", type=Path)
    trust_revoke = trust_commands.add_parser("revoke", help="revoke a trusted key")
    trust_revoke.add_argument("repository", type=Path)
    trust_revoke.add_argument("key_id")
    args = parser.parse_args(argv)

    if args.command == "inspect":
        with Repository(args.repository) as repository:
            for event in repository.events():
                print(json.dumps(_event_dict(event), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "verify":
        with Repository(args.repository) as repository:
            count = repository.verify()
            print(f"OK: {count} event(s), last sequence {repository.last_sequence}")
        return 0
    if args.command == "extract":
        with Repository(args.repository) as repository:
            created = CandidateService(
                repository, minimum_confidence=args.minimum_confidence
            ).extract_all()
            print(f"Created {len(created)} candidate(s)")
        return 0
    if args.command == "candidates":
        with Repository(args.repository) as repository:
            for event in repository.events():
                if event.event_type == events_pb2.EXPERIENCE_CANDIDATE_CREATED:
                    print(json.dumps(unpack_payload(event), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "export":
        with Repository(args.repository) as repository:
            export_package(repository, args.destination, publisher=args.publisher)
        print(f"Exported {args.destination}")
        return 0
    if args.command == "import":
        with Repository(args.repository) as repository:
            count = import_package(repository, args.source)
        print(f"Imported {count} quarantined experience(s)")
        return 0
    if args.command == "benefits":
        with Repository(args.repository) as repository:
            for event in repository.events():
                if event.event_type != events_pb2.EXPERIENCE_BENEFIT_EVALUATED:
                    continue
                payload = unpack_payload(event)
                if args.experience_id and payload.get("experience_id") != args.experience_id:
                    continue
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "package":
        with Repository(args.repository) as repository:
            service = PackageService(repository)
            if args.package_command in ("inspect", "verify"):
                inspection = service.inspect(args.source, sha256=args.sha256)
                print(json.dumps(inspection.to_dict(), ensure_ascii=False, sort_keys=True))
            elif args.package_command == "mount":
                mount_report = service.mount(args.source, sha256=args.sha256)
                print(json.dumps(mount_report.to_dict(), ensure_ascii=False, sort_keys=True))
            elif args.package_command == "list":
                for mounted in service.mounts():
                    print(json.dumps(mounted.to_dict(), ensure_ascii=False, sort_keys=True))
            elif args.package_command == "export":
                signer = PackageSigner.load(args.signing_key) if args.signing_key else None
                exported_path = service.export(
                    args.destination,
                    name=args.name,
                    version=args.package_version,
                    publisher=args.publisher,
                    signer=signer,
                )
                print(f"Exported {exported_path}")
            elif args.package_command == "upgrade":
                upgraded = service.upgrade(args.name, args.source, sha256=args.sha256)
                print(json.dumps(upgraded.to_dict(), ensure_ascii=False, sort_keys=True))
            elif args.package_command == "rollback":
                rolled_back = service.rollback(args.name)
                print(json.dumps(rolled_back.to_dict(), ensure_ascii=False, sort_keys=True))
            elif args.package_command == "unmount":
                unmounted = service.unmount(args.name)
                print(json.dumps(unmounted.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "trust":
        with Repository(args.repository) as repository:
            store = PackageService(repository).trust_store
            if args.trust_command == "add":
                identifier = store.add(load_public_key(args.public_key), alias=args.alias)
                print(identifier)
            elif args.trust_command == "list":
                print(json.dumps(store.entries(), ensure_ascii=False, sort_keys=True))
            elif args.trust_command == "revoke":
                store.revoke(args.key_id)
                print(f"Revoked {args.key_id}")
        return 0
    parser.print_help()
    return 0


def _event_dict(event: events_pb2.EventEnvelope) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": events_pb2.EventType.Name(event.event_type),
        "repository_id": event.repository_id,
        "run_id": event.run_id,
        "sequence_number": event.sequence_number,
        "timestamp": event.timestamp.ToJsonString(),
        "producer": event.producer,
        "attributes": dict(event.attributes),
        "payload": unpack_payload(event),
    }
