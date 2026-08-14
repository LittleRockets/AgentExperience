from __future__ import annotations

import unittest

from agent_experience.schema import events_pb2, experience_pb2


class SchemaTests(unittest.TestCase):
    def test_event_envelope_round_trip(self) -> None:
        envelope = events_pb2.EventEnvelope(
            event_id="event-1",
            event_type=events_pb2.RUN_STARTED,
            schema_version=1,
            repository_id="repo-1",
            run_id="run-1",
            sequence_number=1,
            producer="unit-test",
        )

        restored = events_pb2.EventEnvelope.FromString(envelope.SerializeToString())

        self.assertEqual(restored.event_id, "event-1")
        self.assertEqual(restored.event_type, events_pb2.RUN_STARTED)

    def test_experience_uses_typed_arguments(self) -> None:
        definition = experience_pb2.ExperienceDefinition(
            experience_id="experience-1",
            revision_id="revision-1",
            generation=1,
            schema_version=1,
            experience_type=experience_pb2.TASK_STRATEGY,
            status=experience_pb2.CANDIDATE,
            summary="A validated strategy candidate",
        )
        node = definition.strategy.nodes.add(
            node_id="search",
            tool=experience_pb2.ToolContract(
                contract_id="mcp://trusted/search@schema-hash",
                provider="mcp",
                name="search",
                idempotent=True,
            ),
        )
        node.arguments["limit"].integer_value = 5

        restored = experience_pb2.ExperienceDefinition.FromString(definition.SerializeToString())

        self.assertEqual(restored.strategy.nodes[0].arguments["limit"].integer_value, 5)


if __name__ == "__main__":
    unittest.main()
