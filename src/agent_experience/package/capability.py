"""Automatic local capability catalog and deterministic package binding."""

from __future__ import annotations

import hashlib
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .model import (
    CapabilityBinding,
    CapabilityRequirement,
    CompatibilityStatus,
    ReasonCode,
)


@dataclass(frozen=True, slots=True)
class LocalCapability:
    capability_id: str
    implementation_id: str
    version: str
    schema_fingerprint: str
    aliases: tuple[str, ...] = ()


class CapabilityCatalog:
    def __init__(self) -> None:
        self._values: dict[str, LocalCapability] = {}

    def register_callable(
        self,
        function: Callable[..., Any],
        implementation_id: str,
        *,
        capability: str = "",
    ) -> LocalCapability:
        capability_id, version = _normalize_capability(
            capability or f"capability://{_slug(function.__name__)}@1"
        )
        signature = str(inspect.signature(function))
        value = LocalCapability(
            capability_id,
            implementation_id,
            version,
            hashlib.sha256(signature.encode("utf-8")).hexdigest(),
            aliases=(implementation_id,),
        )
        self._values[implementation_id] = value
        self._values[capability_id] = value
        return value

    def values(self) -> tuple[LocalCapability, ...]:
        return tuple({value.implementation_id: value for value in self._values.values()}.values())

    def implementation(self, implementation_id: str) -> LocalCapability | None:
        value = self._values.get(implementation_id)
        return value if value and value.implementation_id == implementation_id else None

    def bind(self, requirement: CapabilityRequirement) -> CapabilityBinding:
        exact = self._values.get(requirement.capability_id)
        if exact is not None:
            return CapabilityBinding(
                requirement.capability_id,
                exact.implementation_id,
                CompatibilityStatus.COMPATIBLE,
                ReasonCode.OK,
            )
        alias_matches = {
            value.implementation_id: value
            for alias in requirement.aliases
            for value in self.values()
            if alias == value.implementation_id or alias in value.aliases
        }
        if len(alias_matches) == 1:
            value = next(iter(alias_matches.values()))
            return CapabilityBinding(
                requirement.capability_id,
                value.implementation_id,
                CompatibilityStatus.COMPATIBLE_WITH_BINDING,
                ReasonCode.OK,
            )
        if len(alias_matches) > 1:
            return CapabilityBinding(
                requirement.capability_id,
                status=CompatibilityStatus.NEEDS_BINDING,
                reason=ReasonCode.CAPABILITY_AMBIGUOUS,
            )
        return CapabilityBinding(
            requirement.capability_id,
            status=CompatibilityStatus.NEEDS_BINDING,
            reason=ReasonCode.CAPABILITY_MISSING,
        )


def _normalize_capability(value: str) -> tuple[str, str]:
    normalized = value if value.startswith("capability://") else f"capability://{value}"
    if "@" not in normalized:
        normalized += "@1"
    identifier, version = normalized.rsplit("@", 1)
    if not identifier.removeprefix("capability://") or not version:
        raise ValueError("capability must identify a name and version")
    return f"{identifier}@{version}", version


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unnamed"
