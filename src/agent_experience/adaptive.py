"""Deterministic, explainable and fail-closed v0.3 experience selection."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol

from agent_experience.policy import PolicyObject, RiskLevel

_TOKEN = re.compile(r"[\w\-]+", re.UNICODE)


class AdaptiveDecision(str, Enum):
    SELECTED = "selected"
    REJECTED = "rejected"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class SelectionContext:
    task: str
    goal: str = ""
    task_type: str = ""
    framework: str = ""
    model_id: str = ""
    available_tools: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    environment: Mapping[str, Any] = field(default_factory=dict)
    state: Mapping[str, Any] = field(default_factory=dict)
    max_prompt_tokens: int | None = None
    max_latency_ms: float | None = None
    max_tool_cost: float | None = None
    max_risk: RiskLevel = RiskLevel.MEDIUM

    def __post_init__(self) -> None:
        if not self.task:
            raise ValueError("selection context task must not be empty")
        for value in (self.max_prompt_tokens, self.max_latency_ms, self.max_tool_cost):
            if value is not None and value < 0:
                raise ValueError("selection budgets must not be negative")
        object.__setattr__(self, "available_tools", frozenset(self.available_tools))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        object.__setattr__(self, "state", MappingProxyType(dict(self.state)))


@dataclass(frozen=True, slots=True)
class ScoreComponents:
    applicability: float
    expected_benefit: float
    cost: float
    risk: float
    uncertainty: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in self.values()):
            raise ValueError("score components must be finite")
        if not 0.0 <= self.applicability <= 1.0:
            raise ValueError("applicability must be between 0 and 1")
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("uncertainty must be between 0 and 1")

    def values(self) -> tuple[float, ...]:
        return (
            self.applicability,
            self.expected_benefit,
            self.cost,
            self.risk,
            self.uncertainty,
        )

    @property
    def net_benefit(self) -> float:
        return self.applicability * self.expected_benefit - self.cost - self.risk - self.uncertainty


class PolicyScorer(Protocol):
    """Optional scorer. Hard constraints are evaluated before this interface is called."""

    scorer_id: str
    version: str

    def score(self, policy: PolicyObject, context: SelectionContext) -> ScoreComponents: ...


@dataclass(frozen=True, slots=True)
class SelectorConfig:
    minimum_confidence: float = 0.0
    minimum_net_benefit: float = -1.0
    max_candidates: int = 100
    max_composition: int = 1
    selector_version: str = "0.3.0"

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum confidence must be between 0 and 1")
        if self.max_candidates <= 0 or self.max_composition <= 0:
            raise ValueError("selector bounds must be positive")


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    decision: AdaptiveDecision
    experience_id: str = ""
    revision_id: str = ""
    policy_hash: str = ""
    score: ScoreComponents | None = None
    reason_codes: tuple[str, ...] = ()
    scorer_id: str = "deterministic-rule-v1"
    rank: int = 0


@dataclass(frozen=True, slots=True)
class SelectionBatch:
    decisions: tuple[CandidateDecision, ...]
    selector_version: str
    composite_experience_ids: tuple[str, ...] = ()
    shadow_scores: Mapping[str, ScoreComponents] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "shadow_scores", MappingProxyType(dict(self.shadow_scores)))

    @property
    def selected(self) -> tuple[CandidateDecision, ...]:
        return tuple(item for item in self.decisions if item.decision is AdaptiveDecision.SELECTED)


class DeterministicPolicyScorer:
    scorer_id = "deterministic-rule-v1"
    version = "1"

    def score(self, policy: PolicyObject, context: SelectionContext) -> ScoreComponents:
        query = _tokens(" ".join(value for value in (context.task, context.goal) if value))
        document = _tokens(" ".join((policy.summary, *policy.trigger_keywords)))
        lexical = len(query & document) / max(1, len(query | document))
        structured = 1.0 if context.task_type and context.task_type in policy.task_types else 0.0
        applicability = min(1.0, lexical + 0.35 * structured + 0.05 * len(policy.evidence))
        cost = min(1.0, policy.cost.prompt_tokens / max(1, context.max_prompt_tokens or 1024)) * 0.2
        cost += min(1.0, policy.cost.latency_ms / max(1.0, context.max_latency_ms or 1000.0)) * 0.1
        risk = {
            RiskLevel.LOW: 0.0,
            RiskLevel.MEDIUM: 0.1,
            RiskLevel.HIGH: 0.3,
            RiskLevel.UNKNOWN: 0.4,
        }[policy.risk]
        expected = max(policy.expected_effect.benefit, policy.confidence * applicability)
        uncertainty = policy.expected_effect.uncertainty * 0.25
        return ScoreComponents(applicability, expected, cost, risk, uncertainty)


class AdaptiveSelector:
    """Bounded selection pipeline with hard filters, scoring, tie-break and composition."""

    def __init__(
        self,
        config: SelectorConfig | None = None,
        *,
        scorer: PolicyScorer | None = None,
        shadow_scorer: PolicyScorer | None = None,
    ) -> None:
        self.config = config or SelectorConfig()
        self.scorer = scorer
        self.shadow_scorer = shadow_scorer
        self._fallback = DeterministicPolicyScorer()

    def select(
        self,
        policies: Sequence[PolicyObject],
        context: SelectionContext,
        *,
        limit: int = 5,
    ) -> SelectionBatch:
        if limit <= 0:
            raise ValueError("selection limit must be positive")
        bounded = sorted(policies, key=lambda item: (item.experience_id, item.revision_id))[
            : self.config.max_candidates
        ]
        if not bounded:
            return SelectionBatch(
                (CandidateDecision(AdaptiveDecision.ABSTAINED, reason_codes=("NO_CANDIDATES",)),),
                self.config.selector_version,
            )
        rejected: list[CandidateDecision] = []
        ranked: list[tuple[PolicyObject, ScoreComponents, str, tuple[str, ...]]] = []
        shadow: dict[str, ScoreComponents] = {}
        for policy in bounded:
            failures = self._hard_filter(policy, context)
            if failures:
                rejected.append(self._decision(policy, AdaptiveDecision.REJECTED, failures))
                continue
            score, scorer_id, score_reasons = self._score(policy, context)
            if self.shadow_scorer is not None:
                try:
                    shadow[policy.experience_id] = self.shadow_scorer.score(policy, context)
                except Exception:
                    pass
            soft_failures: list[str] = []
            if score.net_benefit < self.config.minimum_net_benefit:
                soft_failures.append("NON_POSITIVE_NET_BENEFIT")
            if soft_failures:
                rejected.append(
                    self._decision(
                        policy, AdaptiveDecision.REJECTED, tuple(soft_failures), score, scorer_id
                    )
                )
                continue
            ranked.append((policy, score, scorer_id, score_reasons))
        ranked.sort(
            key=lambda item: (
                -item[1].net_benefit,
                -item[0].priority,
                -item[0].confidence,
                item[0].experience_id,
                item[0].revision_id,
            )
        )
        chosen = self._compose(ranked, min(limit, self.config.max_composition))
        selected_ids = {item[0].experience_id for item in chosen}
        selected: list[CandidateDecision] = []
        for rank, (policy, score, scorer_id, reasons) in enumerate(chosen, start=1):
            selected.append(
                self._decision(
                    policy,
                    AdaptiveDecision.SELECTED,
                    ("HARD_CONSTRAINTS_SATISFIED", "V0_3_DETERMINISTIC_SELECTION", *reasons),
                    score,
                    scorer_id,
                    rank,
                )
            )
        for policy, score, scorer_id, _ in ranked:
            if policy.experience_id not in selected_ids:
                rejected.append(
                    self._decision(
                        policy,
                        AdaptiveDecision.REJECTED,
                        ("LOWER_DETERMINISTIC_RANK",),
                        score,
                        scorer_id,
                    )
                )
        decisions: tuple[CandidateDecision, ...]
        if selected:
            decisions = tuple(selected + rejected)
        else:
            decisions = (
                CandidateDecision(
                    AdaptiveDecision.ABSTAINED,
                    reason_codes=("NO_POLICY_PASSED_SELECTION",),
                ),
                *rejected,
            )
        return SelectionBatch(
            decisions,
            self.config.selector_version,
            tuple(item.experience_id for item in selected),
            shadow,
        )

    def _hard_filter(self, policy: PolicyObject, context: SelectionContext) -> tuple[str, ...]:
        reasons: list[str] = []
        if not policy.is_current():
            reasons.append("POLICY_NOT_CURRENT")
        if policy.task_types and context.task_type not in policy.task_types:
            reasons.append("TASK_TYPE_MISMATCH")
        if policy.required_frameworks and context.framework not in policy.required_frameworks:
            reasons.append("FRAMEWORK_MISMATCH")
        if not policy.required_tools.issubset(context.available_tools):
            reasons.append("REQUIRED_TOOL_MISSING")
        if not policy.required_capabilities.issubset(context.capabilities):
            reasons.append("REQUIRED_CAPABILITY_MISSING")
        if any(context.environment.get(key) != value for key, value in policy.environment.items()):
            reasons.append("ENVIRONMENT_MISMATCH")
        combined = {**context.environment, **context.state}
        if any(not _condition_matches(condition, combined) for condition in policy.preconditions):
            reasons.append("PRECONDITION_FAILED")
        if any(
            _condition_matches(condition, combined) for condition in policy.forbidden_conditions
        ):
            reasons.append("FORBIDDEN_CONDITION_PRESENT")
        if policy.risk > context.max_risk:
            reasons.append("RISK_BUDGET_EXCEEDED")
        if (
            context.max_prompt_tokens is not None
            and policy.cost.prompt_tokens > context.max_prompt_tokens
        ):
            reasons.append("PROMPT_TOKEN_BUDGET_EXCEEDED")
        if context.max_latency_ms is not None and policy.cost.latency_ms > context.max_latency_ms:
            reasons.append("LATENCY_BUDGET_EXCEEDED")
        if context.max_tool_cost is not None and policy.cost.tool_cost > context.max_tool_cost:
            reasons.append("TOOL_COST_BUDGET_EXCEEDED")
        if policy.confidence < self.config.minimum_confidence:
            reasons.append("CONFIDENCE_BELOW_THRESHOLD")
        return tuple(reasons)

    def _score(
        self, policy: PolicyObject, context: SelectionContext
    ) -> tuple[ScoreComponents, str, tuple[str, ...]]:
        if self.scorer is None:
            return self._fallback.score(policy, context), self._fallback.scorer_id, ()
        try:
            result = self.scorer.score(policy, context)
            return (
                result,
                f"{self.scorer.scorer_id}/{self.scorer.version}",
                ("PLUGGABLE_SCORER_USED",),
            )
        except Exception:
            return (
                self._fallback.score(policy, context),
                self._fallback.scorer_id,
                ("SCORER_FAILED_SAFE_FALLBACK",),
            )

    @staticmethod
    def _decision(
        policy: PolicyObject,
        decision: AdaptiveDecision,
        reasons: tuple[str, ...],
        score: ScoreComponents | None = None,
        scorer_id: str = "deterministic-rule-v1",
        rank: int = 0,
    ) -> CandidateDecision:
        return CandidateDecision(
            decision,
            policy.experience_id,
            policy.revision_id,
            policy.revision_hash,
            score,
            reasons,
            scorer_id,
            rank,
        )

    @staticmethod
    def _compose(
        ranked: Sequence[tuple[PolicyObject, ScoreComponents, str, tuple[str, ...]]],
        limit: int,
    ) -> list[tuple[PolicyObject, ScoreComponents, str, tuple[str, ...]]]:
        chosen: list[tuple[PolicyObject, ScoreComponents, str, tuple[str, ...]]] = []
        paths: set[str] = set()
        for item in ranked:
            policy = item[0]
            if chosen:
                if not all(
                    policy.experience_id in other[0].composable_with
                    and other[0].experience_id in policy.composable_with
                    for other in chosen
                ):
                    continue
                if any(
                    policy.experience_id in other[0].conflicts_with
                    or other[0].experience_id in policy.conflicts_with
                    for other in chosen
                ):
                    continue
                if paths & set(policy.policy_delta):
                    continue
            chosen.append(item)
            paths.update(policy.policy_delta)
            if len(chosen) >= limit:
                break
        return chosen


def _tokens(text: str) -> set[str]:
    return {value.lower() for value in _TOKEN.findall(text)}


def _condition_matches(condition: str, state: Mapping[str, Any]) -> bool:
    """Evaluate the deliberately small, non-executable precondition language."""

    if "!=" in condition:
        key, expected = (part.strip() for part in condition.split("!=", 1))
        return key in state and str(state[key]) != expected
    if "=" in condition:
        key, expected = (part.strip() for part in condition.split("=", 1))
        return key in state and str(state[key]) == expected
    return bool(state.get(condition.strip()))
