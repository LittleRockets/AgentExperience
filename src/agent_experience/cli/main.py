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
