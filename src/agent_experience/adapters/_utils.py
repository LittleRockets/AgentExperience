"""Safe duck-typed extraction helpers for optional framework objects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_experience.security import RedactionPolicy


def get_value(value: object, name: str, default: Any = None) -> Any:
    """Read an attribute or mapping key without depending on a framework class."""

    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def object_summary(value: object, policy: RedactionPolicy) -> Any:
    """Extract a bounded representation suitable for an observation event."""

    if value is None:
        return None
    if hasattr(value, "model_dump"):
        try:
            return policy.sanitize(value.model_dump(mode="json"))
        except (TypeError, ValueError):
            pass
    return policy.sanitize(value)
