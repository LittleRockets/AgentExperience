"""Reproducible offline evaluation contracts for adaptive selection."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from statistics import NormalDist, mean


@dataclass(frozen=True, slots=True)
class SelectionObservation:
    """One holdout decision paired with a counterfactual no-experience outcome."""

    sample_id: str
    split: str
    source_id: str
    selected: bool
    beneficial: bool
    confidence: float
    outcome_value: float
    baseline_value: float
    task_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.sample_id or self.split not in {"train", "dev", "holdout"}:
            raise ValueError("observation requires an id and a train/dev/holdout split")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("observation confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SelectionEvaluation:
    schema_version: str
    sample_count: int
    selection_precision: float
    negative_transfer_rate: float
    coverage: float
    abstention_quality: float
    calibration_error: float
    net_benefit: float
    net_benefit_ci_low: float
    net_benefit_ci_high: float
    leakage_free: bool
    reason_codes: tuple[str, ...]

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=indent)


def evaluate_selection(
    observations: tuple[SelectionObservation, ...],
    *,
    confidence_level: float = 0.95,
    calibration_bins: int = 10,
) -> SelectionEvaluation:
    """Measure holdout selection quality with a paired normal confidence interval."""

    if not observations:
        raise ValueError("selection evaluation requires observations")
    if not 0.5 < confidence_level < 1.0 or calibration_bins <= 0:
        raise ValueError("invalid evaluation configuration")
    leakage = _leakage_reasons(observations)
    holdout = tuple(item for item in observations if item.split == "holdout")
    if not holdout:
        raise ValueError("selection evaluation requires holdout observations")
    selected = tuple(item for item in holdout if item.selected)
    abstained = tuple(item for item in holdout if not item.selected)
    precision = sum(item.beneficial for item in selected) / len(selected) if selected else 0.0
    negative = sum(not item.beneficial for item in selected) / len(selected) if selected else 0.0
    coverage = len(selected) / len(holdout)
    abstention_quality = (
        sum(not item.beneficial for item in abstained) / len(abstained) if abstained else 1.0
    )
    calibration = _expected_calibration_error(selected, calibration_bins)
    paired = [item.outcome_value - item.baseline_value for item in holdout]
    net = mean(paired)
    if len(paired) > 1:
        variance = sum((value - net) ** 2 for value in paired) / (len(paired) - 1)
        standard_error = math.sqrt(variance / len(paired))
        z = NormalDist().inv_cdf(0.5 + confidence_level / 2)
        low, high = net - z * standard_error, net + z * standard_error
    else:
        low = high = net
    reasons = tuple(leakage) or ("EVALUATION_VALID",)
    return SelectionEvaluation(
        "0.3",
        len(holdout),
        precision,
        negative,
        coverage,
        abstention_quality,
        calibration,
        net,
        low,
        high,
        not leakage,
        reasons,
    )


def _leakage_reasons(observations: tuple[SelectionObservation, ...]) -> list[str]:
    reasons: list[str] = []
    seen_samples: dict[str, str] = {}
    seen_sources: dict[str, str] = {}
    seen_tasks: dict[str, str] = {}
    for item in observations:
        if item.sample_id in seen_samples and seen_samples[item.sample_id] != item.split:
            reasons.append("SAMPLE_SPLIT_LEAKAGE")
        if item.source_id in seen_sources and seen_sources[item.source_id] != item.split:
            reasons.append("SOURCE_SPLIT_LEAKAGE")
        if (
            item.task_fingerprint
            and item.task_fingerprint in seen_tasks
            and seen_tasks[item.task_fingerprint] != item.split
        ):
            reasons.append("TASK_SPLIT_LEAKAGE")
        seen_samples[item.sample_id] = item.split
        seen_sources[item.source_id] = item.split
        if item.task_fingerprint:
            seen_tasks[item.task_fingerprint] = item.split
    return sorted(set(reasons))


def _expected_calibration_error(observations: tuple[SelectionObservation, ...], bins: int) -> float:
    if not observations:
        return 0.0
    total = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        values = tuple(
            item
            for item in observations
            if lower <= item.confidence <= upper and (index == bins - 1 or item.confidence < upper)
        )
        if values:
            accuracy = sum(item.beneficial for item in values) / len(values)
            confidence = mean(item.confidence for item in values)
            total += len(values) / len(observations) * abs(accuracy - confidence)
    return total
