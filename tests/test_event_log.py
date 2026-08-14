from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_experience.storage.event_log import (
    CorruptRecordError,
    Durability,
    EventLog,
    InvalidLogError,
    SequenceError,
)

REPOSITORY_ID = bytes.fromhex("00112233445566778899aabbccddeeff")
TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class EventLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_round_trip_and_reopen(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "events.bin"
            with EventLog(path, REPOSITORY_ID, durability=Durability.STRICT_DURABLE) as log:
                first = log.append(b"first", sequence_number=1, record_type=1)
                second = log.append(b"second", sequence_number=2, record_type=2, flags=3)
                self.assertGreater(second.offset, first.offset)

            with EventLog(path, REPOSITORY_ID) as reopened:
                self.assertEqual(reopened.last_sequence, 2)
                records = list(reopened.records())

            self.assertEqual([record.payload for record in records], [b"first", b"second"])
            self.assertEqual(records[1].flags, 3)

    def test_rejects_non_monotonic_sequence(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            with EventLog(Path(directory) / "events.bin", REPOSITORY_ID) as log:
                log.append(b"first", sequence_number=1, record_type=1)
                with self.assertRaises(SequenceError):
                    log.append(b"duplicate", sequence_number=1, record_type=1)

    def test_recovers_incomplete_tail(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "events.bin"
            with EventLog(path, REPOSITORY_ID) as log:
                record = log.append(b"complete", sequence_number=1, record_type=1)
            valid_size = record.offset + record.total_length
            with path.open("ab") as file:
                file.write(b"AEXR\x00")

            with EventLog(path, REPOSITORY_ID) as recovered:
                self.assertEqual(recovered.last_sequence, 1)
                self.assertEqual([item.payload for item in recovered.records()], [b"complete"])
            self.assertEqual(path.stat().st_size, valid_size)

    def test_detects_checksum_corruption(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "events.bin"
            with EventLog(path, REPOSITORY_ID) as log:
                record = log.append(b"payload", sequence_number=1, record_type=1)
            with path.open("r+b") as file:
                file.seek(record.offset + record.total_length - 1)
                byte = file.read(1)
                file.seek(-1, 1)
                file.write(bytes([byte[0] ^ 0xFF]))

            with self.assertRaises(CorruptRecordError):
                EventLog(path, REPOSITORY_ID)

    def test_rejects_wrong_repository(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "events.bin"
            EventLog(path, REPOSITORY_ID).close()
            with self.assertRaises(InvalidLogError):
                EventLog(path, b"0" * 16)


if __name__ == "__main__":
    unittest.main()
