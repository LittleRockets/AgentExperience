from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from agent_experience.events.factory import unpack_payload
from agent_experience.observer import capture
from agent_experience.schema import events_pb2
from agent_experience.storage import ProjectionRunner, Repository

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_append_reopen_and_verify(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "repo"
            with Repository(path) as repository:
                repository_id = repository.repository_id
                event = repository.append_event(
                    events_pb2.RUN_STARTED,
                    run_id="run-1",
                    producer="test",
                    payload={"task": "answer", "attempt": 1},
                )
                self.assertEqual(event.sequence_number, 1)

            with Repository(path) as reopened:
                reopened.append_event(
                    events_pb2.RUN_COMPLETED,
                    run_id="run-1",
                    producer="test",
                    payload={"success": True},
                )
                events = list(reopened.events())
                self.assertEqual(reopened.repository_id, repository_id)
                self.assertEqual(reopened.verify(), 2)

            self.assertEqual([event.sequence_number for event in events], [1, 2])
            self.assertEqual(unpack_payload(events[0])["task"], "answer")

    def test_projection_resumes_from_watermark(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:
                for index in range(3):
                    repository.append_event(
                        events_pb2.RUN_STARTED,
                        run_id=f"run-{index}",
                        producer="test",
                    )
                seen: list[int] = []
                runner = ProjectionRunner(repository, "test")
                self.assertEqual(runner.run(lambda event: seen.append(event.sequence_number)), 3)
                self.assertEqual(runner.run(lambda event: seen.append(event.sequence_number)), 3)
                self.assertEqual(seen, [1, 2, 3])

    def test_sync_capture_preserves_result_and_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:

                @capture(repository)
                def double(value: int) -> int:
                    return value * 2

                @capture(repository)
                def fail() -> None:
                    raise RuntimeError("expected")

                self.assertEqual(double(3), 6)
                with self.assertRaisesRegex(RuntimeError, "expected"):
                    fail()
                types = [event.event_type for event in repository.events()]

            self.assertEqual(
                types,
                [
                    events_pb2.RUN_STARTED,
                    events_pb2.RUN_COMPLETED,
                    events_pb2.RUN_STARTED,
                    events_pb2.RUN_FAILED,
                ],
            )

    def test_async_capture_preserves_coroutine_behavior(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with Repository(Path(directory) / "repo") as repository:

                @capture(repository)
                async def increment(value: int) -> int:
                    await asyncio.sleep(0)
                    return value + 1

                self.assertEqual(asyncio.run(increment(4)), 5)
                self.assertEqual(repository.verify(), 2)


if __name__ == "__main__":
    unittest.main()
