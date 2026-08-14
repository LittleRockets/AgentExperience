"""Framework- and domain-neutral extension contracts.

Integrations own semantic extraction.  The core only consumes normalized features,
baseline fingerprints, and token estimates.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

from agent_experience.experience.delta import RunFeatures
from agent_experience.schema import experience_pb2

T = TypeVar("T", contravariant=True)


class FeatureExtractor(Protocol[T]):
    def extract(self, value: T, *, context: Mapping[str, Any] | None = None) -> RunFeatures: ...


class BaselineResolver(Protocol[T]):
    def resolve(self, value: T) -> experience_pb2.BaselineProfile: ...


class TokenEstimator(Protocol):
    def estimate(self, text: str, *, model_id: str = "") -> int: ...


class Utf8TokenEstimator:
    """Dependency-free approximation; applications may inject a model tokenizer."""

    def estimate(self, text: str, *, model_id: str = "") -> int:
        del model_id
        if not text:
            return 0
        return max(1, (len(text.encode("utf-8")) + 3) // 4)
