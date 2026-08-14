"""Rule-level applicability, baseline deduplication, and token-budget enforcement."""

from __future__ import annotations

from dataclasses import dataclass

from agent_experience.schema import events_pb2, experience_pb2
from agent_experience.storage import Repository


@dataclass(frozen=True, slots=True)
class TokenBudget:
    max_context_tokens: int
    base_input_tokens: int
    reserved_output_tokens: int
    max_experience_tokens: int = 128

    @property
    def available_experience_tokens(self) -> int:
        context_available = (
            self.max_context_tokens - self.base_input_tokens - self.reserved_output_tokens
        )
        return max(0, min(self.max_experience_tokens, context_available))


@dataclass(frozen=True, slots=True)
class RuleSelection:
    selected: tuple[experience_pb2.DeltaRule, ...]
    rejected_rule_ids: tuple[str, ...]
    estimated_tokens: int
    rendered: str


class RuleSelector:
    def select(
        self,
        definition: experience_pb2.ExperienceDefinition,
        budget: TokenBudget,
        *,
        baseline_paths: frozenset[str] = frozenset(),
    ) -> RuleSelection:
        if definition.mode != experience_pb2.PROMPT_DELTA:
            return RuleSelection((), (), 0, "")
        available = budget.available_experience_tokens
        selected: list[experience_pb2.DeltaRule] = []
        rejected: list[str] = []
        used = 0
        rules = sorted(definition.delta.rules, key=lambda rule: (-rule.priority, rule.rule_id))
        for rule in rules:
            if rule.path in baseline_paths or used + rule.estimated_tokens > available:
                rejected.append(rule.rule_id)
                continue
            selected.append(rule)
            used += rule.estimated_tokens
        rendered = "\n".join(_render_rule(rule) for rule in selected)
        return RuleSelection(tuple(selected), tuple(rejected), used, rendered)

    def select_and_record(
        self,
        repository: Repository,
        definition: experience_pb2.ExperienceDefinition,
        budget: TokenBudget,
        *,
        run_id: str,
        baseline_paths: frozenset[str] = frozenset(),
    ) -> RuleSelection:
        selection = self.select(definition, budget, baseline_paths=baseline_paths)
        event_type = (
            events_pb2.EXPERIENCE_RULE_SELECTED
            if selection.selected
            else events_pb2.EXPERIENCE_REJECTED_BY_BUDGET
        )
        repository.append_event(
            event_type,
            run_id=run_id,
            producer="rule-selector/v1",
            payload={
                "experience_id": definition.experience_id,
                "revision_id": definition.revision_id,
                "selected_rule_ids": [rule.rule_id for rule in selection.selected],
                "rejected_rule_ids": list(selection.rejected_rule_ids),
                "estimated_tokens": selection.estimated_tokens,
                "available_tokens": budget.available_experience_tokens,
            },
        )
        return selection


def _render_rule(rule: experience_pb2.DeltaRule) -> str:
    kind = rule.value.WhichOneof("kind")
    value = getattr(rule.value, kind) if kind else ""
    operator = experience_pb2.RuleOperator.Name(rule.operator)
    return f"{rule.path} {operator} {value}"
