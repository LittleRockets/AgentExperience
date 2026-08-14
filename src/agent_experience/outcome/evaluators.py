"""Deterministic task outcome evaluation primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Generic, Protocol, TypeVar

R = TypeVar("R")
R_contra = TypeVar("R_contra", contravariant=True)


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Evaluation:
    """A result classification with auditable evidence references."""

    outcome: Outcome
    confidence: float
    evaluator_id: str
    evaluator_version: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("evaluation confidence must be between 0 and 1")


class OutcomeEvaluator(Protocol[R_contra]):
    """Protocol implemented by result evaluators."""

    def evaluate(self, result: R_contra) -> Evaluation:
        """Evaluate a successful function return value."""


@dataclass(frozen=True, slots=True)
class PredicateEvaluator(Generic[R]):
    """Classify a result using a deterministic predicate."""

    predicate: Callable[[R], bool]
    evaluator_id: str
    evaluator_version: str = "1"
    success_evidence: str = "predicate returned true"
    failure_evidence: str = "predicate returned false"

    def evaluate(self, result: R) -> Evaluation:
        success = self.predicate(result)
        return Evaluation(
            outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
            confidence=1.0,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            evidence=(self.success_evidence if success else self.failure_evidence,),
        )
