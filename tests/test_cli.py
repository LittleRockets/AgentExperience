from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agent_experience.cli.main import main
from agent_experience.package import PackageService
from agent_experience.schema import events_pb2, experience_pb2
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

    def test_package_inspect_mount_and_list(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "shared.exp"
            with Repository(root / "source") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=experience_pb2.ExperienceDefinition(
                        experience_id="exp",
                        revision_id="rev",
                        generation=1,
                        schema_version=1,
                        content_hash=b"content",
                        experience_type=experience_pb2.CONSTRAINT,
                        status=experience_pb2.ACTIVE,
                        summary="Keep output structured",
                    ),
                )
                PackageService(source).export(package, name="shared", version="1.0.0")
            target = root / "target"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["package", "inspect", str(target), str(package)]), 0)
            self.assertEqual(json.loads(output.getvalue())["package_name"], "shared")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["package", "mount", str(target), str(package)]), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "mounted_in_quarantine")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["package", "list", str(target)]), 0)
            self.assertEqual(json.loads(output.getvalue())["package_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
