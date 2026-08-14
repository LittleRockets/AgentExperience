"""Pure package/runtime compatibility preflight."""

from __future__ import annotations

import platform
from dataclasses import dataclass

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from agent_experience._version import __version__

from .capability import CapabilityCatalog
from .model import CapabilityBinding, CompatibilityStatus, PackageInspection, ReasonCode


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    status: CompatibilityStatus
    reason: ReasonCode
    bindings: tuple[CapabilityBinding, ...]
    missing_frameworks: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()


def resolve_compatibility(
    inspection: PackageInspection,
    *,
    agent_requires: str,
    python_requires: str,
    catalog: CapabilityCatalog,
    frameworks: frozenset[str],
) -> CompatibilityReport:
    messages: list[str] = []
    if not _matches(agent_requires, __version__) or not _matches(
        python_requires, platform.python_version()
    ):
        return CompatibilityReport(
            CompatibilityStatus.INCOMPATIBLE,
            ReasonCode.VERSION_INCOMPATIBLE,
            (),
            messages=("AgentExperience or Python version constraint is not satisfied",),
        )
    missing_frameworks = tuple(
        value for value in inspection.required_frameworks if value not in frameworks
    )
    bindings = tuple(catalog.bind(value) for value in inspection.requirements)
    missing_required = [
        value
        for value, requirement in zip(bindings, inspection.requirements, strict=True)
        if value.status == CompatibilityStatus.NEEDS_BINDING and not requirement.optional
    ]
    if missing_frameworks:
        messages.append("missing framework integrations: " + ", ".join(missing_frameworks))
    if missing_required:
        messages.append(
            "missing or ambiguous capabilities: "
            + ", ".join(value.required for value in missing_required)
        )
    if missing_frameworks:
        status, reason = CompatibilityStatus.INCOMPATIBLE, ReasonCode.FRAMEWORK_MISSING
    elif missing_required:
        status, reason = CompatibilityStatus.NEEDS_BINDING, missing_required[0].reason
    elif any(value.status == CompatibilityStatus.COMPATIBLE_WITH_BINDING for value in bindings):
        status, reason = CompatibilityStatus.COMPATIBLE_WITH_BINDING, ReasonCode.OK
    else:
        status, reason = CompatibilityStatus.COMPATIBLE, ReasonCode.OK
    return CompatibilityReport(
        status,
        reason,
        bindings,
        missing_frameworks,
        tuple(messages),
    )


def _matches(specifier: str, version: str) -> bool:
    if not specifier:
        return True
    try:
        return Version(version) in SpecifierSet(specifier)
    except (InvalidSpecifier, ValueError):
        return False
