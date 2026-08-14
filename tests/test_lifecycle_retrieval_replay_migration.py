from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_experience import (
    ExperienceRetriever,
    LifecycleManager,
    PromotionPolicy,
    ReplayExecutor,
    Repository,
    RetrievalQuery,
    export_package,
    import_package,
    validate_dag,
)
from agent_experience.observer import ToolRegistry, ToolSpec
from agent_experience.schema import common_pb2, events_pb2, experience_pb2

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


def definition(status: int = experience_pb2.CANDIDATE) -> experience_pb2.ExperienceDefinition:
    return experience_pb2.ExperienceDefinition(
        experience_id="exp-1",
        revision_id="rev-1",
        generation=1,
        schema_version=1,
        content_hash=b"semantic-hash",
        experience_type=experience_pb2.TASK_STRATEGY,
        status=status,
        summary="Search documentation safely",
        strategy=experience_pb2.DAG(
            nodes=[
                experience_pb2.DAGNode(
                    node_id="search",
                    tool=experience_pb2.ToolContract(
                        contract_id="local://search@1",
                        name="search",
                        idempotent=True,
                        has_external_side_effects=False,
                    ),
                    arguments={
                        "query": common_pb2.TypedValue(
                            reference=common_pb2.ValueReference(
                                type=common_pb2.ValueReference.RUN_INPUT,
                                path="query",
                            )
                        )
                    },
                )
            ],
            output_node_ids=["search"],
        ),
        source_run_ids=["source-run"],
    )


def evaluation(
    run_id: str, outcome: int = experience_pb2.EvaluationEvent.SUCCESS
) -> experience_pb2.EvaluationEvent:
    return experience_pb2.EvaluationEvent(
        evaluation_id=f"eval-{run_id}",
        experience_id="exp-1",
        revision_id="rev-1",
        run_id=run_id,
        outcome=outcome,
        confidence=1.0,
        evaluator_id="deterministic-test",
        evaluator_version="1",
    )


class LifecycleReplayMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_lifecycle_retrieval_and_replay(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:
                repository.append_event(
                    events_pb2.EXPERIENCE_CANDIDATE_CREATED,
                    run_id="source-run",
                    producer="test",
                    payload=definition(),
                )
                manager = LifecycleManager(repository, PromotionPolicy(2, 3, 2, True))
                manager.record_evaluation(evaluation("run-a"))
                manager.record_evaluation(evaluation("run-b"))
                validated = manager.promote("exp-1")
                manager.record_evaluation(evaluation("run-c"))
                with self.assertRaises(PermissionError):
                    manager.promote("exp-1")
                active = manager.promote("exp-1", manual_approval=True)
                active.replay_allowed = True
                # Publish the policy-bearing revision without mutating the existing event.
                active.revision_id = "replay-enabled"
                active.generation += 1
                repository.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test-policy",
                    payload=active,
                )
                self.assertEqual(validated.status, experience_pb2.VALIDATED)

                advice = ExperienceRetriever(repository).search(RetrievalQuery("search docs"))
                self.assertEqual(len(advice), 1)
                self.assertIn("UNTRUSTED", advice[0].warning)

                registry = ToolRegistry()
                registry.register(
                    ToolSpec(
                        "local://search@1",
                        "search",
                        lambda query: query.upper(),
                        idempotent=True,
                        has_external_side_effects=False,
                    )
                )
                result = ReplayExecutor(repository, registry).execute(
                    active, {"query": "docs"}, verifier=lambda outputs: outputs["search"] == "DOCS"
                )
                self.assertTrue(result.verified)
                self.assertEqual(result.outputs["search"], "DOCS")
                self.assertEqual(validate_dag(active), ("search",))

    def test_export_import_is_quarantined_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "shared.exp"
            active = definition(experience_pb2.ACTIVE)
            with Repository(root / "source") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED, run_id="", producer="test", payload=active
                )
                export_package(source, package, publisher="unit-test")
            with Repository(root / "target") as target:
                self.assertEqual(import_package(target, package), 1)
                self.assertEqual(import_package(target, package), 0)
                imported = next(
                    event
                    for event in target.events()
                    if event.event_type == events_pb2.EXPERIENCE_IMPORTED
                )
                value = experience_pb2.ExperienceDefinition()
                self.assertTrue(imported.payload.Unpack(value))
                self.assertEqual(value.status, experience_pb2.QUARANTINED)
                self.assertFalse(value.replay_allowed)


if __name__ == "__main__":
    unittest.main()
