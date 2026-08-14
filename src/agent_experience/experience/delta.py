"""Baseline-relative, deterministic experience delta mining."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass

from agent_experience.schema import common_pb2, experience_pb2


def build_baseline_profile(
    baseline_id: str,
    baseline_version: str,
    *,
    system_prompt: str = "",
    workflow: str | bytes = b"",
    tool_contract_ids: tuple[str, ...] = (),
    model_id: str = "",
    output_contract: str | bytes = b"",
) -> experience_pb2.BaselineProfile:
    """Build a stable profile used to invalidate deltas when their baseline changes."""

    if not baseline_id or not baseline_version:
        raise ValueError("baseline_id and baseline_version are required")
    return experience_pb2.BaselineProfile(
        baseline_id=baseline_id,
        baseline_version=baseline_version,
        system_prompt_hash=_hash(system_prompt),
        workflow_hash=_hash(workflow),
        toolset_hash=_hash("\n".join(sorted(tool_contract_ids))),
        model_id=model_id,
        output_contract_hash=_hash(output_contract),
    )


@dataclass(frozen=True, slots=True)
class RunFeatures:
    """Compact structured evidence; never contains the original model output."""

    run_id: str
    passed_constraints: frozenset[str]
    failed_constraints: frozenset[str] = frozenset()
    tool_sequence: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass(frozen=True, slots=True)
class MiningResult:
    delta: experience_pb2.ExperienceDelta
    source_run_ids: tuple[str, ...]
    used_llm: bool = False
    mining_input_tokens: int = 0
    mining_output_tokens: int = 0
    mining_latency_ms: int = 0


class DeterministicMiner:
    """Mine only common, baseline-novel facts without an LLM call."""

    def mine(
        self,
        baseline: experience_pb2.BaselineProfile,
        runs: tuple[RunFeatures, ...],
        *,
        baseline_constraints: frozenset[str] = frozenset(),
    ) -> MiningResult:
        started_ns = time.perf_counter_ns()
        if len({run.run_id for run in runs}) < 2:
            raise ValueError("at least two independent runs are required")
        common = set(runs[0].passed_constraints)
        for run in runs[1:]:
            common.intersection_update(run.passed_constraints)
        novel = sorted(common - baseline_constraints)
        rules: list[experience_pb2.DeltaRule] = []
        evidence = sorted({run.run_id for run in runs})
        for index, constraint in enumerate(novel):
            rules.append(
                experience_pb2.DeltaRule(
                    rule_id=f"constraint-{index + 1}",
                    path=f"output.constraints.{constraint}",
                    operator=experience_pb2.REQUIRES,
                    value=common_pb2.TypedValue(boolean_value=True),
                    evidence_run_ids=evidence,
                    confidence=1.0,
                    rationale="constraint passed in every independent successful run",
                    priority=100 - index,
                    estimated_tokens=_estimate_tokens(constraint),
                )
            )
        sequences = {run.tool_sequence for run in runs if run.tool_sequence}
        if len(sequences) == 1:
            sequence = next(iter(sequences))
            if sequence:
                text = " -> ".join(sequence)
                rules.append(
                    experience_pb2.DeltaRule(
                        rule_id="common-tool-sequence",
                        path="workflow.tool_sequence",
                        operator=experience_pb2.EQUALS,
                        value=common_pb2.TypedValue(string_value=text),
                        evidence_run_ids=evidence,
                        confidence=1.0,
                        rationale="identical tool sequence observed in every successful run",
                        priority=80,
                        estimated_tokens=_estimate_tokens(text),
                    )
                )
        canonical = {
            "baseline": baseline.SerializeToString(deterministic=True).hex(),
            "rules": [rule.SerializeToString(deterministic=True).hex() for rule in rules],
        }
        digest = _hash(json.dumps(canonical, sort_keys=True).encode())
        delta = experience_pb2.ExperienceDelta(
            baseline=baseline,
            rules=rules,
            estimated_prompt_tokens=sum(rule.estimated_tokens for rule in rules),
            canonical_hash=digest,
        )
        elapsed_ms = max(0, (time.perf_counter_ns() - started_ns) // 1_000_000)
        return MiningResult(delta, tuple(evidence), mining_latency_ms=elapsed_ms)


def definition_from_delta(
    result: MiningResult,
    *,
    task_type: str,
    created_by: str = "agent-experience.deterministic-miner/v1",
) -> experience_pb2.ExperienceDefinition:
    """Create an immutable Candidate whose semantic content is the delta itself."""

    digest = result.delta.canonical_hash
    definition = experience_pb2.ExperienceDefinition(
        experience_id=f"exp-{digest.hex()[:24]}",
        revision_id=str(uuid.uuid4()),
        generation=1,
        schema_version=2,
        content_hash=digest,
        experience_type=experience_pb2.CONSTRAINT,
        status=experience_pb2.CANDIDATE,
        created_by=created_by,
        summary=f"{len(result.delta.rules)} baseline-relative deterministic rule(s)",
        source_run_ids=result.source_run_ids,
        mode=experience_pb2.PROMPT_DELTA,
        delta=result.delta,
        mining_input_tokens=result.mining_input_tokens,
        mining_output_tokens=result.mining_output_tokens,
        mining_latency_ms=result.mining_latency_ms,
    )
    definition.applicability.task_types.append(task_type)
    return definition


def _hash(value: str | bytes) -> bytes:
    """Hash public text/bytes inputs with one stable UTF-8 normalization rule."""

    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(encoded).digest()


def _estimate_tokens(value: str) -> int:
    return max(1, (len(value.encode("utf-8")) + 3) // 4)
