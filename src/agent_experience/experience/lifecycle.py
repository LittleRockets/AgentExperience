"""Evidence-driven immutable experience lifecycle management."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from google.protobuf import timestamp_pb2

from agent_experience.benefit import BenefitLedger, BreakEvenPolicy
from agent_experience.schema import events_pb2, experience_pb2
from agent_experience.storage.repository import Repository


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    """Configurable evidence thresholds; no candidate is activated from one success."""

    validated_successes: int = 2
    active_successes: int = 3
    quarantine_failures: int = 2
    require_manual_approval_for_active: bool = True


class ExperienceCatalog:
    """Rebuild current revisions and evaluation evidence from the event log."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def definitions(self) -> dict[str, experience_pb2.ExperienceDefinition]:
        result: dict[str, experience_pb2.ExperienceDefinition] = {}
        definition_events = {
            events_pb2.EXPERIENCE_CANDIDATE_CREATED,
            events_pb2.EXPERIENCE_REVISION_PUBLISHED,
            events_pb2.EXPERIENCE_ACTIVATED,
            events_pb2.EXPERIENCE_DEPRECATED,
            events_pb2.EXPERIENCE_QUARANTINED,
            events_pb2.EXPERIENCE_TOMBSTONED,
            events_pb2.EXPERIENCE_IMPORTED,
        }
        for event in self.repository.events():
            if event.event_type in definition_events:
                value = experience_pb2.ExperienceDefinition()
                if event.payload.Unpack(value):
                    result[value.experience_id] = value
        return result

    def evaluations(self, experience_id: str) -> tuple[experience_pb2.EvaluationEvent, ...]:
        values: list[experience_pb2.EvaluationEvent] = []
        for event in self.repository.events():
            if event.event_type == events_pb2.EXPERIENCE_EVALUATED:
                value = experience_pb2.EvaluationEvent()
                if event.payload.Unpack(value) and value.experience_id == experience_id:
                    values.append(value)
        return tuple(values)


class LifecycleManager:
    """Append evaluations and legal lifecycle transitions as new revisions."""

    def __init__(self, repository: Repository, policy: PromotionPolicy | None = None) -> None:
        self.repository = repository
        self.policy = policy or PromotionPolicy()

    def record_evaluation(self, evaluation: experience_pb2.EvaluationEvent) -> None:
        if not evaluation.experience_id or not evaluation.revision_id:
            raise ValueError("evaluation must identify an experience revision")
        self.repository.append_event(
            events_pb2.EXPERIENCE_EVALUATED,
            run_id=evaluation.run_id,
            producer=evaluation.evaluator_id or "experience-evaluator",
            payload=evaluation,
        )

    def promote(
        self, experience_id: str, *, manual_approval: bool = False
    ) -> experience_pb2.ExperienceDefinition:
        catalog = ExperienceCatalog(self.repository)
        current = catalog.definitions().get(experience_id)
        if current is None:
            raise KeyError(experience_id)
        evaluations = catalog.evaluations(experience_id)
        successes = len(
            {
                item.run_id
                for item in evaluations
                if item.outcome == experience_pb2.EvaluationEvent.SUCCESS
            }
        )
        failures = len(
            {
                item.run_id
                for item in evaluations
                if item.outcome == experience_pb2.EvaluationEvent.FAILURE
            }
        )
        if failures >= self.policy.quarantine_failures:
            return self.transition(current, experience_pb2.QUARANTINED)
        if (
            current.status == experience_pb2.CANDIDATE
            and successes >= self.policy.validated_successes
        ):
            return self.transition(current, experience_pb2.VALIDATED)
        if current.status == experience_pb2.VALIDATED and successes >= self.policy.active_successes:
            if self.policy.require_manual_approval_for_active and not manual_approval:
                raise PermissionError("manual approval is required before activation")
            return self.transition(current, experience_pb2.ACTIVE)
        raise ValueError("configured promotion evidence threshold is not satisfied")

    def promote_with_benefit(
        self,
        experience_id: str,
        policy: BreakEvenPolicy,
        *,
        manual_approval: bool = False,
    ) -> experience_pb2.ExperienceDefinition:
        """Activate a VALIDATED revision only when recorded holdout benefit is acceptable."""

        current = ExperienceCatalog(self.repository).definitions().get(experience_id)
        if current is None:
            raise KeyError(experience_id)
        if current.status != experience_pb2.VALIDATED:
            raise ValueError("benefit promotion requires a VALIDATED revision")
        aggregate = BenefitLedger(self.repository).aggregate(
            experience_id, revision_id=current.revision_id, window=policy.evaluation_window
        )
        decision = policy.evaluate(aggregate)
        if not decision.accepted:
            raise ValueError("benefit policy rejected activation: " + ", ".join(decision.reasons))
        if self.policy.require_manual_approval_for_active and not manual_approval:
            raise PermissionError("manual approval is required before activation")
        return self.transition(current, experience_pb2.ACTIVE)

    def enforce_benefit(
        self,
        experience_id: str,
        policy: BreakEvenPolicy,
    ) -> experience_pb2.ExperienceDefinition:
        """Quarantine an ACTIVE/VALIDATED revision after a rejected measured application."""

        current = ExperienceCatalog(self.repository).definitions().get(experience_id)
        if current is None:
            raise KeyError(experience_id)
        aggregate = BenefitLedger(self.repository).aggregate(
            experience_id, revision_id=current.revision_id, window=policy.evaluation_window
        )
        decision = policy.evaluate(aggregate)
        if decision.accepted:
            return current
        if current.status not in (experience_pb2.ACTIVE, experience_pb2.VALIDATED):
            raise ValueError("only ACTIVE or VALIDATED revisions can be benefit-quarantined")
        return self.transition(current, experience_pb2.QUARANTINED)

    def transition(
        self, current: experience_pb2.ExperienceDefinition, status: int
    ) -> experience_pb2.ExperienceDefinition:
        allowed = {
            experience_pb2.CANDIDATE: {
                experience_pb2.VALIDATED,
                experience_pb2.QUARANTINED,
                experience_pb2.TOMBSTONED,
            },
            experience_pb2.VALIDATED: {
                experience_pb2.ACTIVE,
                experience_pb2.QUARANTINED,
                experience_pb2.TOMBSTONED,
            },
            experience_pb2.ACTIVE: {experience_pb2.DEPRECATED, experience_pb2.QUARANTINED},
            experience_pb2.DEPRECATED: {experience_pb2.TOMBSTONED},
            experience_pb2.QUARANTINED: {experience_pb2.CANDIDATE, experience_pb2.TOMBSTONED},
        }
        if status not in allowed.get(current.status, set()):
            raise ValueError("illegal experience lifecycle transition")
        revision = experience_pb2.ExperienceDefinition()
        revision.CopyFrom(current)
        revision.parent_revision_ids.append(current.revision_id)
        revision.revision_id = str(uuid.uuid4())
        revision.generation += 1
        revision.status = status
        revision.created_at.CopyFrom(_now())
        event_type = {
            experience_pb2.VALIDATED: events_pb2.EXPERIENCE_REVISION_PUBLISHED,
            experience_pb2.ACTIVE: events_pb2.EXPERIENCE_ACTIVATED,
            experience_pb2.DEPRECATED: events_pb2.EXPERIENCE_DEPRECATED,
            experience_pb2.QUARANTINED: events_pb2.EXPERIENCE_QUARANTINED,
            experience_pb2.TOMBSTONED: events_pb2.EXPERIENCE_TOMBSTONED,
            experience_pb2.CANDIDATE: events_pb2.EXPERIENCE_REVISION_PUBLISHED,
        }[status]
        self.repository.append_event(
            event_type, run_id="", producer="lifecycle/v1", payload=revision
        )
        return revision


def _now() -> timestamp_pb2.Timestamp:
    value = timestamp_pb2.Timestamp()
    value.FromNanoseconds(time.time_ns())
    return value
