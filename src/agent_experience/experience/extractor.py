"""Conservative extraction of variableized candidate experiences."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, cast

from google.protobuf import timestamp_pb2

from agent_experience.schema import common_pb2, experience_pb2

from .trace import RunTrace


class CandidateExtractor:
    """Build candidates only from successfully completed, explicitly evaluated traces."""

    def __init__(self, *, minimum_confidence: float = 0.8) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self.minimum_confidence = minimum_confidence

    def extract(self, trace: RunTrace) -> tuple[experience_pb2.ExperienceDefinition, ...]:
        if not trace.is_eligible(self.minimum_confidence):
            return ()
        kinds = [experience_pb2.TASK_STRATEGY, experience_pb2.VALIDATION]
        if trace.tool_starts:
            kinds.append(experience_pb2.TOOL_ROUTING)
        if trace.has_recovery:
            kinds.append(experience_pb2.RECOVERY)
        return tuple(self._definition(trace, kind) for kind in kinds)

    def _definition(self, trace: RunTrace, kind: int) -> experience_pb2.ExperienceDefinition:
        nodes: list[experience_pb2.DAGNode] = []
        for index, entry in enumerate(trace.tool_starts):
            payload = entry.payload
            node_id = f"tool-{index + 1}"
            arguments: dict[str, common_pb2.TypedValue] = {}
            raw_kwargs = payload.get("kwargs")
            if isinstance(raw_kwargs, dict):
                for key in sorted(raw_kwargs):
                    arguments[key] = common_pb2.TypedValue(
                        reference=common_pb2.ValueReference(
                            type=common_pb2.ValueReference.RUN_INPUT,
                            path=f"tools.{index}.kwargs.{key}",
                        )
                    )
            raw_args = payload.get("args")
            if isinstance(raw_args, list):
                for position in range(len(raw_args)):
                    key = f"arg_{position}"
                    arguments[key] = common_pb2.TypedValue(
                        reference=common_pb2.ValueReference(
                            type=common_pb2.ValueReference.RUN_INPUT,
                            path=f"tools.{index}.args.{position}",
                        )
                    )
            tool = experience_pb2.ToolContract(
                contract_id=str(payload.get("contract_id", payload.get("tool_name", "unknown"))),
                name=str(payload.get("tool_name", "unknown")),
                version_constraint=str(payload.get("tool_version", "")),
                idempotent=bool(payload.get("idempotent", False)),
                has_external_side_effects=bool(payload.get("has_external_side_effects", True)),
            )
            nodes.append(
                experience_pb2.DAGNode(
                    node_id=node_id,
                    tool=tool,
                    arguments=arguments,
                    depends_on=[f"tool-{index}"] if index else [],
                )
            )
        strategy = experience_pb2.DAG(
            nodes=nodes,
            output_node_ids=[nodes[-1].node_id] if nodes else [],
        )
        fingerprint = {
            "experience_type": kind,
            "strategy": strategy.SerializeToString(deterministic=True).hex(),
            "success_criteria": ["source run completed with a verified successful outcome"],
        }
        digest = hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).digest()
        created_at = timestamp_pb2.Timestamp()
        created_at.FromNanoseconds(time.time_ns())
        kind_name = experience_pb2.ExperienceType.Name(kind).lower().replace("_", " ")
        return experience_pb2.ExperienceDefinition(
            experience_id=f"exp-{digest.hex()[:24]}",
            revision_id=str(uuid.uuid4()),
            generation=1,
            schema_version=1,
            content_hash=digest,
            experience_type=cast(Any, kind),
            status=experience_pb2.CANDIDATE,
            created_at=created_at,
            created_by="agent-experience.extractor/v1",
            summary=f"Candidate {kind_name} derived from a verified successful run",
            strategy=strategy,
            success_criteria=["source run completed with a verified successful outcome"],
            source_run_ids=[trace.run_id],
            replay_allowed=False,
            exact_cache_allowed=False,
        )
