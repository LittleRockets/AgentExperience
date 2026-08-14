"""Framed, append-only event log used as the repository source of truth.

The log is deliberately independent of Protobuf. Payloads are opaque bytes, allowing schema
evolution without coupling storage recovery to a particular generated message version.
"""

from __future__ import annotations

import os
import struct
import threading
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO

FILE_MAGIC = b"AEXPLOG\x00"
RECORD_MAGIC = b"AEXR"
FILE_FORMAT_VERSION = 1
RECORD_FORMAT_VERSION = 1
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024

_FILE_HEADER = struct.Struct(">8sH16sQ")
_RECORD_HEADER = struct.Struct(">4sHBBQQ")
_CHECKSUM = struct.Struct(">I")


class EventLogError(Exception):
    """Base exception for event-log failures."""


class InvalidLogError(EventLogError):
    """Raised when a file is not a supported AgentExperience event log."""


class CorruptRecordError(EventLogError):
    """Raised when a complete record fails structural or checksum validation."""


class SequenceError(EventLogError):
    """Raised when a caller attempts to append a non-monotonic sequence."""


class Durability(str, Enum):
    """Flush policy applied after appending a record."""

    BEST_EFFORT = "best_effort"
    RUN_DURABLE = "run_durable"
    STRICT_DURABLE = "strict_durable"


@dataclass(frozen=True, slots=True)
class LogRecord:
    """A validated record read from the event log."""

    offset: int
    sequence_number: int
    record_type: int
    flags: int
    payload: bytes
    total_length: int


class EventLog:
    """Single-writer append-only log with CRC32 protected frames.

    Args:
        path: File path for the segment.
        repository_id: Stable 16-byte repository identifier. It is written when creating a new
            segment and checked when opening an existing segment.
        durability: Default flush policy for appends.
        max_payload_bytes: Defensive upper bound checked before writes and reads.

    The class serializes writers inside one process. Cross-process writers are intentionally not
    supported in the first milestone and must be prevented by the repository layer.
    """

    def __init__(
        self,
        path: Path,
        repository_id: bytes,
        *,
        durability: Durability = Durability.RUN_DURABLE,
        max_payload_bytes: int = MAX_PAYLOAD_BYTES,
    ) -> None:
        if len(repository_id) != 16:
            raise ValueError("repository_id must be exactly 16 bytes")
        if max_payload_bytes <= 0:
            raise ValueError("max_payload_bytes must be positive")

        self.path = Path(path)
        self.repository_id = repository_id
        self.durability = durability
        self.max_payload_bytes = max_payload_bytes
        self._lock = threading.Lock()
        self._file: BinaryIO | None = None
        self._last_sequence = 0

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._open_and_recover()

    @property
    def last_sequence(self) -> int:
        """Return the highest committed sequence number."""

        return self._last_sequence

    def append(
        self,
        payload: bytes,
        *,
        sequence_number: int,
        record_type: int,
        flags: int = 0,
        durability: Durability | None = None,
    ) -> LogRecord:
        """Append and return one complete framed record.

        Sequence numbers must be strictly increasing. ``record_type`` and ``flags`` are one-byte
        unsigned values reserved for the domain-event envelope and storage features.
        """

        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if len(payload) > self.max_payload_bytes:
            raise ValueError("payload exceeds configured maximum")
        if not 0 <= record_type <= 255 or not 0 <= flags <= 255:
            raise ValueError("record_type and flags must fit in one byte")

        with self._lock:
            file = self._require_open()
            if sequence_number <= self._last_sequence:
                raise SequenceError(
                    f"sequence {sequence_number} is not greater than {self._last_sequence}"
                )

            header = _RECORD_HEADER.pack(
                RECORD_MAGIC,
                RECORD_FORMAT_VERSION,
                record_type,
                flags,
                sequence_number,
                len(payload),
            )
            checksum = _CHECKSUM.pack(zlib.crc32(header + payload) & 0xFFFFFFFF)
            file.seek(0, os.SEEK_END)
            offset = file.tell()
            frame = header + payload + checksum
            file.write(frame)
            self._apply_durability(durability or self.durability)
            self._last_sequence = sequence_number
            return LogRecord(
                offset=offset,
                sequence_number=sequence_number,
                record_type=record_type,
                flags=flags,
                payload=payload,
                total_length=len(frame),
            )

    def records(self, *, start_offset: int | None = None) -> Iterator[LogRecord]:
        """Iterate complete, validated records from the segment."""

        file = self._require_open()
        file.flush()
        with self.path.open("rb") as reader:
            self._read_file_header(reader)
            reader.seek(start_offset if start_offset is not None else _FILE_HEADER.size)
            while record := self._read_record(reader, allow_incomplete_tail=False):
                yield record

    def flush(self, *, sync: bool = False) -> None:
        """Flush buffered writes and optionally request an operating-system sync."""

        with self._lock:
            file = self._require_open()
            file.flush()
            if sync:
                os.fsync(file.fileno())

    def close(self) -> None:
        """Flush and close the segment. Calling close repeatedly is safe."""

        with self._lock:
            if self._file is not None:
                self._file.flush()
                self._file.close()
                self._file = None

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _open_and_recover(self) -> None:
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        self._file = self.path.open("w+b" if is_new else "r+b")
        try:
            if is_new:
                self._file.write(
                    _FILE_HEADER.pack(FILE_MAGIC, FILE_FORMAT_VERSION, self.repository_id, 0)
                )
                self._file.flush()
                os.fsync(self._file.fileno())
                return

            self._read_file_header(self._file)
            last_good_offset = _FILE_HEADER.size
            last_sequence = 0
            while record := self._read_record(self._file, allow_incomplete_tail=True):
                if record.sequence_number <= last_sequence:
                    raise CorruptRecordError("record sequence numbers are not strictly increasing")
                last_sequence = record.sequence_number
                last_good_offset = record.offset + record.total_length

            actual_size = self._file.seek(0, os.SEEK_END)
            if actual_size != last_good_offset:
                self._file.truncate(last_good_offset)
                self._file.flush()
                os.fsync(self._file.fileno())
            self._last_sequence = last_sequence
        except BaseException:
            self._file.close()
            self._file = None
            raise

    def _read_file_header(self, file: BinaryIO) -> None:
        file.seek(0)
        raw = file.read(_FILE_HEADER.size)
        if len(raw) != _FILE_HEADER.size:
            raise InvalidLogError("event log has an incomplete file header")
        magic, version, repository_id, _created_at = _FILE_HEADER.unpack(raw)
        if magic != FILE_MAGIC:
            raise InvalidLogError("event log magic does not match")
        if version != FILE_FORMAT_VERSION:
            raise InvalidLogError(f"unsupported event log format version: {version}")
        if repository_id != self.repository_id:
            raise InvalidLogError("event log belongs to a different repository")

    def _read_record(self, file: BinaryIO, *, allow_incomplete_tail: bool) -> LogRecord | None:
        offset = file.tell()
        header = file.read(_RECORD_HEADER.size)
        if not header:
            return None
        if len(header) != _RECORD_HEADER.size:
            if allow_incomplete_tail:
                return None
            raise CorruptRecordError("incomplete record header")

        magic, version, record_type, flags, sequence_number, payload_length = _RECORD_HEADER.unpack(
            header
        )
        if magic != RECORD_MAGIC:
            raise CorruptRecordError(f"invalid record magic at offset {offset}")
        if version != RECORD_FORMAT_VERSION:
            raise CorruptRecordError(f"unsupported record version at offset {offset}: {version}")
        if payload_length > self.max_payload_bytes:
            raise CorruptRecordError("record payload exceeds configured maximum")

        payload = file.read(payload_length)
        checksum_raw = file.read(_CHECKSUM.size)
        if len(payload) != payload_length or len(checksum_raw) != _CHECKSUM.size:
            if allow_incomplete_tail:
                return None
            raise CorruptRecordError("incomplete record payload or checksum")
        expected_checksum = _CHECKSUM.unpack(checksum_raw)[0]
        actual_checksum = zlib.crc32(header + payload) & 0xFFFFFFFF
        if actual_checksum != expected_checksum:
            raise CorruptRecordError(f"checksum mismatch at offset {offset}")

        return LogRecord(
            offset=offset,
            sequence_number=sequence_number,
            record_type=record_type,
            flags=flags,
            payload=payload,
            total_length=_RECORD_HEADER.size + payload_length + _CHECKSUM.size,
        )

    def _apply_durability(self, durability: Durability) -> None:
        file = self._require_open()
        if durability is Durability.BEST_EFFORT:
            return
        file.flush()
        if durability is Durability.STRICT_DURABLE:
            os.fsync(file.fileno())

    def _require_open(self) -> BinaryIO:
        if self._file is None:
            raise EventLogError("event log is closed")
        return self._file
