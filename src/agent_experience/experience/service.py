"""Candidate extraction orchestration and semantic deduplication."""

from __future__ import annotations

import base64

from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2, experience_pb2
from agent_experience.storage.repository import Repository

from .extractor import CandidateExtractor
from .trace import load_traces


class CandidateService:
    def __init__(self, repository: Repository, *, minimum_confidence: float = 0.8) -> None:
        self.repository = repository
        self.extractor = CandidateExtractor(minimum_confidence=minimum_confidence)

    def extract_all(self) -> tuple[experience_pb2.ExperienceDefinition, ...]:
        known = {
            str(unpack_payload(event).get("content_hash", ""))
            for event in self.repository.events()
            if event.event_type == events_pb2.EXPERIENCE_CANDIDATE_CREATED
        }
        created: list[experience_pb2.ExperienceDefinition] = []
        for trace in load_traces(self.repository):
            for candidate in self.extractor.extract(trace):
                encoded_hash = base64.b64encode(candidate.content_hash).decode("ascii")
                if encoded_hash in known or any(
                    item.content_hash == candidate.content_hash for item in created
                ):
                    continue
                self.repository.append_event(
                    events_pb2.EXPERIENCE_CANDIDATE_CREATED,
                    run_id=trace.run_id,
                    producer="agent-experience.extractor/v1",
                    payload=candidate,
                )
                created.append(candidate)
        return tuple(created)
