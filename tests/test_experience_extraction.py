from __future__ import annotations

import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_experience import CandidateService, PredicateEvaluator, Repository, SQLiteProjection
from agent_experience.events.factory import unpack_payload
from agent_experience.observer import ToolRegistry, ToolSpec, capture
from agent_experience.schema import common_pb2, events_pb2, experience_pb2

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class ExperienceExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_verified_run_creates_variableized_deduplicated_candidates(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "repo"
            with Repository(path) as repository:
                registry = ToolRegistry()
                registry.register(
                    ToolSpec(
                        "local://search@1",
                        "search",
                        lambda query: {"count": 1, "query": query},
                        version="1",
                        idempotent=True,
                        has_external_side_effects=False,
                    )
                )
                search = registry.observed("local://search@1", repository)

                @capture(
                    repository,
                    evaluator=PredicateEvaluator(
                        lambda result: result["count"] == 1,
                        evaluator_id="count-check",
                    ),
                )
                def run() -> dict[str, object]:
                    return search("private concrete query")

                run()
                created = CandidateService(repository).extract_all()
                self.assertEqual(len(created), 3)
                self.assertEqual(CandidateService(repository).extract_all(), ())
                strategy = next(
                    item for item in created if item.experience_type == experience_pb2.TASK_STRATEGY
                )
                self.assertEqual(strategy.status, experience_pb2.CANDIDATE)
                self.assertFalse(strategy.replay_allowed)
                argument = strategy.strategy.nodes[0].arguments["arg_0"]
                self.assertEqual(argument.reference.type, common_pb2.ValueReference.RUN_INPUT)
                self.assertNotIn("private concrete query", str(strategy))

                candidate_event = next(
                    event
                    for event in repository.events()
                    if event.event_type == events_pb2.EXPERIENCE_CANDIDATE_CREATED
                )
                payload = unpack_payload(candidate_event)
                self.assertEqual(
                    payload["content_hash"], base64.b64encode(created[0].content_hash).decode()
                )
                with SQLiteProjection(repository) as projection:
                    projection.update()

            connection = sqlite3.connect(path / "index" / "read-model.sqlite")
            try:
                count = connection.execute("SELECT COUNT(*) FROM experience_candidates").fetchone()
            finally:
                connection.close()
            self.assertEqual(count, (3,))

    def test_run_without_verified_success_is_not_eligible(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:

                @capture(repository)
                def run() -> str:
                    return "completed but unevaluated"

                run()
                self.assertEqual(CandidateService(repository).extract_all(), ())


if __name__ == "__main__":
    unittest.main()
