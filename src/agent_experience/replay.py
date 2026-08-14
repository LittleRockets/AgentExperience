"""Validated, registry-only DAG replay with verification and approvals."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from agent_experience.observer import ToolRegistry
from agent_experience.schema import common_pb2, events_pb2, experience_pb2
from agent_experience.storage import Repository


class DAGValidationError(ValueError):
    pass


def validate_dag(definition: experience_pb2.ExperienceDefinition) -> tuple[str, ...]:
    nodes = {node.node_id: node for node in definition.strategy.nodes}
    if not nodes and definition.experience_type != experience_pb2.VALIDATION:
        raise DAGValidationError("strategy must contain at least one node")
    if len(nodes) != len(definition.strategy.nodes):
        raise DAGValidationError("node IDs must be unique")
    for node in nodes.values():
        if not node.tool.contract_id:
            raise DAGValidationError("every node must reference a tool contract")
        if any(dependency not in nodes for dependency in node.depends_on):
            raise DAGValidationError("node dependency does not exist")
    pending = set(nodes)
    ordered: list[str] = []
    while pending:
        ready = sorted(
            node_id for node_id in pending if set(nodes[node_id].depends_on) <= set(ordered)
        )
        if not ready:
            raise DAGValidationError("strategy DAG contains a cycle")
        ordered.extend(ready)
        pending.difference_update(ready)
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class ReplayResult:
    run_id: str
    outputs: Mapping[str, Any]
    verified: bool


class ReplayExecutor:
    def __init__(self, repository: Repository, registry: ToolRegistry) -> None:
        self.repository = repository
        self.registry = registry

    def execute(
        self,
        definition: experience_pb2.ExperienceDefinition,
        bindings: Mapping[str, Any],
        *,
        verifier: Callable[[Mapping[str, Any]], bool],
        approve: Callable[[experience_pb2.DAGNode], bool] | None = None,
    ) -> ReplayResult:
        if definition.status != experience_pb2.ACTIVE or not definition.replay_allowed:
            raise PermissionError("only ACTIVE revisions explicitly allowing replay may execute")
        order = validate_dag(definition)
        nodes = {node.node_id: node for node in definition.strategy.nodes}
        for node in nodes.values():
            spec = self.registry.get(node.tool.contract_id)
            if spec.has_external_side_effects and not node.requires_approval:
                raise PermissionError("side-effecting replay nodes must require approval")
        run_id = str(uuid.uuid4())
        self.repository.append_event(
            events_pb2.EXPERIENCE_REPLAY_STARTED,
            run_id=run_id,
            producer="replay/v1",
            payload={
                "experience_id": definition.experience_id,
                "revision_id": definition.revision_id,
            },
        )
        outputs: dict[str, Any] = {}
        try:
            for node_id in order:
                node = nodes[node_id]
                if node.requires_approval and (approve is None or not approve(node)):
                    raise PermissionError(f"approval denied for node {node_id}")
                kwargs = {
                    key: _resolve(value, bindings, outputs) for key, value in node.arguments.items()
                }
                spec = self.registry.get(node.tool.contract_id)
                attempts = max(1, int(node.retry.max_attempts))
                for attempt in range(attempts):
                    try:
                        outputs[node_id] = spec.function(**kwargs)
                        break
                    except Exception:
                        if attempt + 1 == attempts:
                            raise
                        time.sleep(
                            (node.retry.initial_backoff_ms / 1000)
                            * max(1.0, node.retry.backoff_multiplier**attempt)
                        )
            verified = bool(verifier(outputs))
            if not verified:
                raise RuntimeError("replay output verification failed")
        except BaseException as error:
            self.repository.append_event(
                events_pb2.EXPERIENCE_REPLAY_FAILED,
                run_id=run_id,
                producer="replay/v1",
                payload={
                    "experience_id": definition.experience_id,
                    "error_type": type(error).__name__,
                },
            )
            raise
        self.repository.append_event(
            events_pb2.EXPERIENCE_REPLAY_COMPLETED,
            run_id=run_id,
            producer="replay/v1",
            payload={"experience_id": definition.experience_id, "verified": True},
        )
        return ReplayResult(run_id, outputs, True)


def _resolve(
    value: common_pb2.TypedValue, bindings: Mapping[str, Any], outputs: Mapping[str, Any]
) -> Any:
    kind = value.WhichOneof("kind")
    if kind == "reference":
        if value.reference.type == common_pb2.ValueReference.RUN_INPUT:
            if value.reference.path not in bindings:
                raise KeyError(f"missing input binding: {value.reference.path}")
            return bindings[value.reference.path]
        if value.reference.type == common_pb2.ValueReference.NODE_OUTPUT:
            return outputs[value.reference.source_node_id]
        raise PermissionError("secret and artifact bindings require an external resolver")
    return getattr(value, kind) if kind else None
