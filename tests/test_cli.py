from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agent_experience.cli.main import main
from agent_experience.schema import events_pb2
from agent_experience.storage import Repository

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_inspect_and_verify(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "repo"
            with Repository(path) as repository:
                repository.append_event(
                    events_pb2.RUN_STARTED,
                    run_id="run-1",
                    producer="test",
                    payload={"task": "demo"},
                )

            inspect_output = io.StringIO()
            with contextlib.redirect_stdout(inspect_output):
                self.assertEqual(main(["inspect", str(path)]), 0)
            event = json.loads(inspect_output.getvalue())
            self.assertEqual(event["event_type"], "RUN_STARTED")
            self.assertEqual(event["payload"]["task"], "demo")

            verify_output = io.StringIO()
            with contextlib.redirect_stdout(verify_output):
                self.assertEqual(main(["verify", str(path)]), 0)
            self.assertIn("OK: 1 event(s), last sequence 1", verify_output.getvalue())

    def test_extract_without_outcome_creates_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "repo"
            with Repository(path) as repository:
                repository.append_event(
                    events_pb2.RUN_COMPLETED,
                    run_id="run-1",
                    producer="test",
                )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["extract", str(path)]), 0)
            self.assertEqual(output.getvalue().strip(), "Created 0 candidate(s)")


if __name__ == "__main__":
    unittest.main()
