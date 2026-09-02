"""Versioned, immutable policy objects used by the v0.3 selector.

Policy objects are advice.  They describe when an experience may be useful and
what it would cost; they never mutate a Harness or execute a tool.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from types import MappingProxyType
from typing import Any

from agent_experience.schema import experience_pb2


class RiskLevel(IntEnum):
    """Ordered risk used by hard constraints; unknown risk fails closed."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    UNKNOWN = 4


def _freeze(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class PolicyCost:
    prompt_tokens: int = 0
    latency_ms: float = 0.0
    tool_cost: float = 0.0

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.latency_ms < 0 or self.tool_cost < 0:
            raise ValueError("policy costs must not be negative")


@dataclass(frozen=True, slots=True)
class ExpectedEffect:
    benefit: float = 0.0
    success_rate_delta: float = 0.0
    uncertainty: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("effect uncertainty must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class PolicyObject:
    """Canonical v1 selection policy derived from an experience revision."""

    experience_id: str
    revision_id: str
    summary: str
    task_types: tuple[str, ...] = ()
    trigger_keywords: tuple[str, ...] = ()
    required_frameworks: tuple[str, ...] = ()
    required_tools: frozenset[str] = frozenset()
    required_capabilities: frozenset[str] = frozenset()
    environment: Mapping[str, Any] = field(default_factory=dict)
    preconditions: tuple[str, ...] = ()
    forbidden_conditions: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    policy_delta: Mapping[str, Any] = field(default_factory=dict)
    expected_effect: ExpectedEffect = field(default_factory=ExpectedEffect)
    cost: PolicyCost = field(default_factory=PolicyCost)
    risk: RiskLevel = RiskLevel.UNKNOWN
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()
    valid_from_ns: int = 0
    valid_until_ns: int = 0
    priority: int = 0
    composable_with: frozenset[str] = frozenset()
    conflicts_with: frozenset[str] = frozenset()
    schema_version: str = "1"

    def __post_init__(self) -> None:
        if not self.experience_id or not self.revision_id:
            raise ValueError("policy must identify an experience revision")
        if self.schema_version != "1":
            raise ValueError("unsupported policy schema version")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("policy confidence must be between 0 and 1")
        if self.valid_until_ns and self.valid_from_ns > self.valid_until_ns:
            raise ValueError("policy validity window is inverted")
        object.__setattr__(self, "environment", _freeze(self.environment))
        object.__setattr__(self, "policy_delta", _freeze(self.policy_delta))
        object.__setattr__(self, "task_types", tuple(sorted(set(self.task_types))))
        object.__setattr__(self, "trigger_keywords", tuple(sorted(set(self.trigger_keywords))))
        object.__setattr__(
            self, "required_frameworks", tuple(sorted(set(self.required_frameworks)))
        )
        object.__setattr__(self, "required_tools", frozenset(self.required_tools))
        object.__setattr__(self, "required_capabilities", frozenset(self.required_capabilities))
        object.__setattr__(self, "evidence", tuple(sorted(set(self.evidence))))
        object.__setattr__(self, "composable_with", frozenset(self.composable_with))
        object.__setattr__(self, "conflicts_with", frozenset(self.conflicts_with))

    def to_dict(self) -> dict[str, Any]:
        """Return the stable, JSON-safe representation used for hashes and artifacts."""

        return {
            "schema_version": self.schema_version,
            "experience_id": self.experience_id,
            "revision_id": self.revision_id,
            "summary": self.summary,
            "task_types": list(self.task_types),
            "trigger_keywords": list(self.trigger_keywords),
            "required_frameworks": list(self.required_frameworks),
            "required_tools": sorted(self.required_tools),
            "required_capabilities": sorted(self.required_capabilities),
            "environment": dict(sorted(self.environment.items())),
            "preconditions": list(self.preconditions),
            "forbidden_conditions": list(self.forbidden_conditions),
            "steps": list(self.steps),
            "policy_delta": dict(sorted(self.policy_delta.items())),
            "expected_effect": {
                "benefit": self.expected_effect.benefit,
                "success_rate_delta": self.expected_effect.success_rate_delta,
                "uncertainty": self.expected_effect.uncertainty,
            },
            "cost": {
                "prompt_tokens": self.cost.prompt_tokens,
                "latency_ms": self.cost.latency_ms,
                "tool_cost": self.cost.tool_cost,
            },
            "risk": self.risk.name.lower(),
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "valid_from_ns": self.valid_from_ns,
            "valid_until_ns": self.valid_until_ns,
            "priority": self.priority,
            "composable_with": sorted(self.composable_with),
            "conflicts_with": sorted(self.conflicts_with),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def revision_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def is_current(self, now_ns: int | None = None) -> bool:
        current = time.time_ns() if now_ns is None else now_ns
        return (not self.valid_from_ns or current >= self.valid_from_ns) and (
            not self.valid_until_ns or current <= self.valid_until_ns
        )


def policy_from_definition(definition: experience_pb2.ExperienceDefinition) -> PolicyObject:
    """Migrate a legacy ExperienceDefinition into the v1 Policy Object contract."""

    applicability = definition.applicability
    rules = sorted(definition.delta.rules, key=lambda item: (-item.priority, item.rule_id))
    confidences = [rule.confidence for rule in rules if rule.confidence > 0]
    confidence = (
        sum(confidences) / len(confidences)
        if confidences
        else min(1.0, 0.5 + 0.05 * len(set(definition.source_run_ids)))
    )
    expiry_ns = (
        applicability.expires_at.ToNanoseconds() if applicability.HasField("expires_at") else 0
    )
    steps = tuple(_render_rule(rule) for rule in rules) or tuple(
        f"Use registered tool {node.tool.contract_id} after {', '.join(node.depends_on) or 'start'}"
        for node in definition.strategy.nodes
    )
    delta = {rule.path: _rule_value(rule) for rule in rules}
    return PolicyObject(
        experience_id=definition.experience_id,
        revision_id=definition.revision_id,
        summary=definition.summary,
        task_types=tuple(applicability.task_types),
        trigger_keywords=tuple(applicability.trigger_keywords),
        required_frameworks=tuple(applicability.required_frameworks),
        required_tools=frozenset(tool.contract_id for tool in applicability.required_tools),
        preconditions=tuple(applicability.preconditions),
        forbidden_conditions=tuple(applicability.forbidden_conditions),
        steps=steps,
        policy_delta=delta,
        expected_effect=ExpectedEffect(
            benefit=min(1.0, 0.05 * len(set(definition.source_run_ids))),
            uncertainty=max(0.0, 1.0 - confidence),
        ),
        cost=PolicyCost(prompt_tokens=definition.delta.estimated_prompt_tokens),
        risk=_legacy_risk(definition),
        confidence=confidence,
        evidence=tuple(definition.source_run_ids),
        valid_until_ns=expiry_ns,
        priority=max((rule.priority for rule in rules), default=0),
    )


def _rule_value(rule: experience_pb2.DeltaRule) -> Any:
    kind = rule.value.WhichOneof("kind")
    return getattr(rule.value, kind) if kind else None


def _legacy_risk(definition: experience_pb2.ExperienceDefinition) -> RiskLevel:
    """Conservatively migrate the risk signals available in the legacy schema."""

    if definition.mode == experience_pb2.PROMPT_DELTA:
        return RiskLevel.MEDIUM
    tools = tuple(definition.applicability.required_tools)
    if tools and all(not tool.has_external_side_effects for tool in tools):
        return RiskLevel.LOW
    return RiskLevel.UNKNOWN


def _render_rule(rule: experience_pb2.DeltaRule) -> str:
    return f"{rule.path} {experience_pb2.RuleOperator.Name(rule.operator)} {_rule_value(rule)}"
