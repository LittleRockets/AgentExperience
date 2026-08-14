"""Measured benefit ledger and break-even policy."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from google.protobuf import timestamp_pb2

from agent_experience.schema import events_pb2, experience_pb2
from agent_experience.storage import Repository


@dataclass(frozen=True, slots=True)
class BreakEvenPolicy:
    minimum_quality_delta: float = 0.0
    minimum_net_benefit: float = 0.0
    minimum_holdout_samples: int = 1
    maximum_input_token_increase: int = 256
    reject_truncation: bool = True
    minimum_measurements: int = 1
    evaluation_window: int = 20
    policy_id: str = "default-break-even"
    policy_version: str = "1"

    def evaluate(self, aggregate: BenefitAggregate) -> BenefitDecision:
        checks = (
            (aggregate.measurement_count >= self.minimum_measurements, "insufficient_measurements"),
            (aggregate.sample_count >= self.minimum_holdout_samples, "insufficient_samples"),
            (aggregate.quality_delta >= self.minimum_quality_delta, "quality_below_threshold"),
            (aggregate.success_rate_delta >= 0, "success_rate_regressed"),
            (aggregate.net_benefit > self.minimum_net_benefit, "net_benefit_below_threshold"),
            (
                aggregate.input_token_delta <= self.maximum_input_token_increase,
                "input_token_budget_exceeded",
            ),
            (not (self.reject_truncation and aggregate.truncation_count), "output_truncated"),
        )
        reasons = tuple(reason for accepted, reason in checks if not accepted)
        return BenefitDecision(self.policy_id, self.policy_version, not reasons, reasons, aggregate)

    def accepts(self, measurement: experience_pb2.BenefitMeasurement) -> bool:
        return self.evaluate(BenefitAggregate.from_measurements((measurement,))).accepted


@dataclass(frozen=True, slots=True)
class BenefitAggregate:
    experience_id: str
    revision_id: str
    measurement_count: int
    sample_count: int
    quality_delta: float
    success_rate_delta: float
    input_token_delta: float
    output_token_delta: float
    latency_ms_delta: float
    net_benefit: float
    truncation_count: int

    @classmethod
    def from_measurements(
        cls, measurements: tuple[experience_pb2.BenefitMeasurement, ...]
    ) -> BenefitAggregate:
        if not measurements:
            raise ValueError("at least one benefit measurement is required")
        total = sum(max(1, item.sample_count) for item in measurements)

        def mean(field: str) -> float:
            return (
                sum(
                    float(getattr(item, field)) * max(1, item.sample_count) for item in measurements
                )
                / total
            )

        latest = measurements[-1]
        return cls(
            latest.experience_id,
            latest.revision_id,
            len(measurements),
            total,
            mean("quality_delta"),
            mean("success_rate_delta"),
            mean("input_token_delta"),
            mean("output_token_delta"),
            mean("latency_ms_delta"),
            mean("net_benefit"),
            sum(bool(item.output_truncated) for item in measurements),
        )


@dataclass(frozen=True, slots=True)
class BenefitDecision:
    policy_id: str
    policy_version: str
    accepted: bool
    reasons: tuple[str, ...]
    aggregate: BenefitAggregate


def measure_benefit(
    *,
    experience_id: str,
    revision_id: str,
    baseline_id: str,
    run_id: str,
    quality_delta: float,
    success_rate_delta: float,
    input_token_delta: int,
    output_token_delta: int,
    latency_ms_delta: int,
    mining_tokens: int,
    mining_latency_ms: int,
    expected_reuse_count: int,
    sample_count: int = 1,
    quality_weight: float = 1.0,
    token_cost_weight: float = 0.01,
    latency_cost_weight: float = 0.001,
    output_truncated: bool = False,
) -> experience_pb2.BenefitMeasurement:
    if expected_reuse_count <= 0:
        raise ValueError("expected_reuse_count must be positive")
    amortized_tokens = mining_tokens / expected_reuse_count
    amortized_latency = mining_latency_ms / expected_reuse_count
    net = (
        quality_delta * quality_weight
        - (input_token_delta + output_token_delta + amortized_tokens) * token_cost_weight
        - (latency_ms_delta + amortized_latency) * latency_cost_weight
    )
    measured_at = timestamp_pb2.Timestamp()
    measured_at.FromNanoseconds(time.time_ns())
    return experience_pb2.BenefitMeasurement(
        measurement_id=str(uuid.uuid4()),
        experience_id=experience_id,
        revision_id=revision_id,
        baseline_id=baseline_id,
        run_id=run_id,
        quality_delta=quality_delta,
        success_rate_delta=success_rate_delta,
        input_token_delta=input_token_delta,
        output_token_delta=output_token_delta,
        latency_ms_delta=latency_ms_delta,
        mining_tokens=mining_tokens,
        mining_latency_ms=mining_latency_ms,
        quality_weight=quality_weight,
        token_cost_weight=token_cost_weight,
        latency_cost_weight=latency_cost_weight,
        net_benefit=net,
        sample_count=sample_count,
        output_truncated=output_truncated,
        measured_at=measured_at,
    )


class BenefitLedger:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def record(self, measurement: experience_pb2.BenefitMeasurement) -> None:
        self.repository.append_event(
            events_pb2.EXPERIENCE_BENEFIT_EVALUATED,
            run_id=measurement.run_id,
            producer="benefit-ledger/v1",
            payload=measurement,
        )

    def measurements(self, experience_id: str) -> tuple[experience_pb2.BenefitMeasurement, ...]:
        values: list[experience_pb2.BenefitMeasurement] = []
        for event in self.repository.events():
            if event.event_type != events_pb2.EXPERIENCE_BENEFIT_EVALUATED:
                continue
            value = experience_pb2.BenefitMeasurement()
            if event.payload.Unpack(value) and value.experience_id == experience_id:
                values.append(value)
        return tuple(values)

    def aggregate(
        self,
        experience_id: str,
        *,
        revision_id: str | None = None,
        window: int | None = None,
    ) -> BenefitAggregate:
        values = self.measurements(experience_id)
        if revision_id is not None:
            values = tuple(item for item in values if item.revision_id == revision_id)
        if window is not None:
            if window <= 0:
                raise ValueError("window must be positive")
            values = values[-window:]
        return BenefitAggregate.from_measurements(values)
