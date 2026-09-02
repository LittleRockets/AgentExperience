"""Bounded online-feedback aggregation and negative-transfer drift signals."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SelectionFeedback:
    experience_id: str
    revision_id: str
    selector_version: str
    cohort: str
    beneficial: bool
    reward_delta: float
    observed_ns: int
    applied: bool = True

    def __post_init__(self) -> None:
        if not self.experience_id or not self.revision_id or not self.selector_version:
            raise ValueError("feedback must identify experience, revision and selector")
        if not math.isfinite(self.reward_delta):
            raise ValueError("feedback reward delta must be finite")


@dataclass(frozen=True, slots=True)
class DriftReport:
    experience_id: str
    revision_id: str
    sample_count: int
    weighted_negative_transfer_rate: float
    weighted_reward_delta: float
    cohort_negative_transfer: tuple[tuple[str, float], ...]
    selector_reward: tuple[tuple[str, float], ...]
    quarantine_recommended: bool
    reason_codes: tuple[str, ...]


class DriftMonitor:
    """Apply deterministic recent decay without performing lifecycle mutations."""

    def __init__(
        self,
        *,
        half_life_seconds: float = 7 * 24 * 60 * 60,
        minimum_samples: int = 10,
        maximum_negative_transfer_rate: float = 0.1,
    ) -> None:
        if half_life_seconds <= 0 or minimum_samples <= 0:
            raise ValueError("drift monitor bounds must be positive")
        if not 0.0 <= maximum_negative_transfer_rate <= 1.0:
            raise ValueError("negative transfer threshold must be between 0 and 1")
        self.half_life_seconds = half_life_seconds
        self.minimum_samples = minimum_samples
        self.maximum_negative_transfer_rate = maximum_negative_transfer_rate

    def evaluate(
        self,
        feedback: tuple[SelectionFeedback, ...],
        *,
        now_ns: int | None = None,
    ) -> DriftReport:
        if not feedback:
            raise ValueError("drift evaluation requires feedback")
        identities = {(item.experience_id, item.revision_id) for item in feedback}
        if len(identities) != 1:
            raise ValueError("drift feedback must target one immutable revision")
        current = time.time_ns() if now_ns is None else now_ns
        weights = [self._weight(item.observed_ns, current) for item in feedback]
        total = sum(weights)
        pairs = tuple(zip(feedback, weights, strict=True))
        negative = sum(weight for item, weight in pairs if not item.beneficial)
        reward = sum(item.reward_delta * weight for item, weight in pairs) / total
        cohort: dict[str, list[tuple[SelectionFeedback, float]]] = defaultdict(list)
        selector: dict[str, list[tuple[SelectionFeedback, float]]] = defaultdict(list)
        for item, weight in pairs:
            cohort[item.cohort or "unknown"].append((item, weight))
            selector[item.selector_version].append((item, weight))
        cohort_rates = tuple(
            sorted(
                (
                    key,
                    sum(weight for item, weight in values if not item.beneficial)
                    / sum(weight for _, weight in values),
                )
                for key, values in cohort.items()
            )
        )
        selector_rewards = tuple(
            sorted(
                (
                    key,
                    sum(item.reward_delta * weight for item, weight in values)
                    / sum(weight for _, weight in values),
                )
                for key, values in selector.items()
            )
        )
        rate = negative / total
        enough = len(feedback) >= self.minimum_samples
        quarantine = enough and (rate > self.maximum_negative_transfer_rate or reward < 0)
        reasons: list[str] = []
        if not enough:
            reasons.append("INSUFFICIENT_DRIFT_SAMPLES")
        if rate > self.maximum_negative_transfer_rate:
            reasons.append("NEGATIVE_TRANSFER_THRESHOLD_EXCEEDED")
        if reward < 0:
            reasons.append("WEIGHTED_REWARD_REGRESSED")
        if not reasons:
            reasons.append("NO_DRIFT_DETECTED")
        experience_id, revision_id = next(iter(identities))
        return DriftReport(
            experience_id,
            revision_id,
            len(feedback),
            rate,
            reward,
            cohort_rates,
            selector_rewards,
            quarantine,
            tuple(reasons),
        )

    def _weight(self, observed_ns: int, now_ns: int) -> float:
        age_seconds = max(0.0, (now_ns - observed_ns) / 1_000_000_000)
        return float(0.5 ** (age_seconds / self.half_life_seconds))
