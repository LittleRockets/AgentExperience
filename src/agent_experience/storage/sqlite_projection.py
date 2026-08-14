"""Rebuildable SQLite read model for runs, tools, and outcomes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2

from .repository import Repository


class SQLiteProjection:
    """Project canonical events into query-oriented SQLite tables."""

    def __init__(self, repository: Repository, path: Path | None = None) -> None:
        self.repository = repository
        self.path = path or repository.path / "index" / "read-model.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    @property
    def watermark(self) -> int:
        row = self._connection.execute(
            "SELECT sequence_number FROM projection_watermark WHERE name = 'main'"
        ).fetchone()
        return int(row[0]) if row else 0

    def update(self) -> int:
        """Atomically apply each unprojected event and advance the watermark."""

        for event in self.repository.events(after_sequence=self.watermark):
            with self._connection:
                self._apply(event)
                self._connection.execute(
                    "INSERT INTO projection_watermark(name, sequence_number) VALUES('main', ?) "
                    "ON CONFLICT(name) DO UPDATE SET sequence_number=excluded.sequence_number",
                    (event.sequence_number,),
                )
        return self.watermark

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteProjection:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projection_watermark (
                    name TEXT PRIMARY KEY,
                    sequence_number INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    callable TEXT,
                    status TEXT NOT NULL,
                    started_sequence INTEGER NOT NULL,
                    completed_sequence INTEGER,
                    duration_ns INTEGER,
                    error_type TEXT
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    tool_call_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_sequence INTEGER NOT NULL,
                    completed_sequence INTEGER,
                    duration_ns INTEGER,
                    error_type TEXT
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    run_id TEXT PRIMARY KEY,
                    outcome TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evaluator_id TEXT NOT NULL,
                    evaluator_version TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experience_candidates (
                    content_hash TEXT PRIMARY KEY,
                    experience_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    experience_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_run_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiences (
                    experience_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    experience_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experience_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    experience_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evaluator_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experience_benefits (
                    measurement_id TEXT PRIMARY KEY,
                    experience_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    baseline_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    quality_delta REAL NOT NULL,
                    input_token_delta INTEGER NOT NULL,
                    output_token_delta INTEGER NOT NULL,
                    latency_ms_delta INTEGER NOT NULL,
                    net_benefit REAL NOT NULL,
                    sample_count INTEGER NOT NULL,
                    output_truncated INTEGER NOT NULL,
                    sequence_number INTEGER NOT NULL
                );
                """
            )

    def _apply(self, event: events_pb2.EventEnvelope) -> None:
        payload = unpack_payload(event)
        if event.event_type == events_pb2.RUN_STARTED:
            self._connection.execute(
                "INSERT OR IGNORE INTO runs(run_id, callable, status, started_sequence) "
                "VALUES(?, ?, 'running', ?)",
                (event.run_id, payload.get("callable", ""), event.sequence_number),
            )
        elif event.event_type in (events_pb2.RUN_COMPLETED, events_pb2.RUN_FAILED):
            status = "completed" if event.event_type == events_pb2.RUN_COMPLETED else "failed"
            self._connection.execute(
                "UPDATE runs SET status=?, completed_sequence=?, duration_ns=?, error_type=? "
                "WHERE run_id=?",
                (
                    status,
                    event.sequence_number,
                    int(payload.get("duration_ns", 0)),
                    payload.get("error_type"),
                    event.run_id,
                ),
            )
        elif event.event_type == events_pb2.TOOL_CALL_STARTED:
            self._connection.execute(
                "INSERT OR IGNORE INTO tool_calls(tool_call_id, run_id, contract_id, tool_name, "
                "status, started_sequence) VALUES(?, ?, ?, ?, 'running', ?)",
                (
                    payload["tool_call_id"],
                    event.run_id,
                    payload["contract_id"],
                    payload["tool_name"],
                    event.sequence_number,
                ),
            )
        elif event.event_type in (events_pb2.TOOL_CALL_COMPLETED, events_pb2.TOOL_CALL_FAILED):
            status = "completed" if event.event_type == events_pb2.TOOL_CALL_COMPLETED else "failed"
            self._connection.execute(
                "UPDATE tool_calls SET status=?, completed_sequence=?, duration_ns=?, error_type=? "
                "WHERE tool_call_id=?",
                (
                    status,
                    event.sequence_number,
                    int(payload.get("duration_ns", 0)),
                    payload.get("error_type"),
                    payload["tool_call_id"],
                ),
            )
        elif event.event_type == events_pb2.OUTCOME_EVALUATED:
            self._connection.execute(
                "INSERT INTO outcomes(run_id, outcome, confidence, evaluator_id, "
                "evaluator_version, sequence_number) VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET outcome=excluded.outcome, "
                "confidence=excluded.confidence, evaluator_id=excluded.evaluator_id, "
                "evaluator_version=excluded.evaluator_version, "
                "sequence_number=excluded.sequence_number",
                (
                    event.run_id,
                    payload["outcome"],
                    float(payload["confidence"]),
                    payload["evaluator_id"],
                    payload["evaluator_version"],
                    event.sequence_number,
                ),
            )
        elif event.event_type == events_pb2.EXPERIENCE_CANDIDATE_CREATED:
            source_runs = payload.get("source_run_ids", [])
            self._connection.execute(
                "INSERT OR IGNORE INTO experience_candidates(content_hash, experience_id, "
                "revision_id, experience_type, status, source_run_id, summary, sequence_number) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["content_hash"],
                    payload["experience_id"],
                    payload["revision_id"],
                    payload["experience_type"],
                    payload["status"],
                    source_runs[0] if source_runs else event.run_id,
                    payload.get("summary", ""),
                    event.sequence_number,
                ),
            )
            self._upsert_experience(payload, event.sequence_number)
        elif event.event_type in (
            events_pb2.EXPERIENCE_REVISION_PUBLISHED,
            events_pb2.EXPERIENCE_ACTIVATED,
            events_pb2.EXPERIENCE_DEPRECATED,
            events_pb2.EXPERIENCE_QUARANTINED,
            events_pb2.EXPERIENCE_TOMBSTONED,
            events_pb2.EXPERIENCE_IMPORTED,
        ):
            self._upsert_experience(payload, event.sequence_number)
        elif event.event_type == events_pb2.EXPERIENCE_EVALUATED:
            self._connection.execute(
                "INSERT OR IGNORE INTO experience_evaluations(evaluation_id, experience_id, "
                "revision_id, run_id, outcome, confidence, evaluator_id, sequence_number) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["evaluation_id"],
                    payload["experience_id"],
                    payload["revision_id"],
                    payload.get("run_id", event.run_id),
                    payload["outcome"],
                    float(payload.get("confidence", 0.0)),
                    payload.get("evaluator_id", ""),
                    event.sequence_number,
                ),
            )
        elif event.event_type == events_pb2.EXPERIENCE_BENEFIT_EVALUATED:
            self._connection.execute(
                "INSERT OR IGNORE INTO experience_benefits(measurement_id, experience_id, "
                "revision_id, baseline_id, run_id, quality_delta, input_token_delta, "
                "output_token_delta, latency_ms_delta, net_benefit, sample_count, "
                "output_truncated, sequence_number) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["measurement_id"],
                    payload["experience_id"],
                    payload["revision_id"],
                    payload["baseline_id"],
                    payload.get("run_id", event.run_id),
                    float(payload.get("quality_delta", 0)),
                    int(payload.get("input_token_delta", 0)),
                    int(payload.get("output_token_delta", 0)),
                    int(payload.get("latency_ms_delta", 0)),
                    float(payload.get("net_benefit", 0)),
                    int(payload.get("sample_count", 0)),
                    int(bool(payload.get("output_truncated", False))),
                    event.sequence_number,
                ),
            )

    def _upsert_experience(self, payload: dict[str, object], sequence: int) -> None:
        generation_value = payload.get("generation", 0)
        generation = int(generation_value) if isinstance(generation_value, (str, int)) else 0
        self._connection.execute(
            "INSERT INTO experiences(experience_id, revision_id, generation, experience_type, "
            "status, content_hash, summary, sequence_number) VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(experience_id) DO UPDATE SET revision_id=excluded.revision_id, "
            "generation=excluded.generation, experience_type=excluded.experience_type, "
            "status=excluded.status, content_hash=excluded.content_hash, summary=excluded.summary, "
            "sequence_number=excluded.sequence_number",
            (
                payload["experience_id"],
                payload["revision_id"],
                generation,
                payload["experience_type"],
                payload["status"],
                payload["content_hash"],
                payload.get("summary", ""),
                sequence,
            ),
        )
