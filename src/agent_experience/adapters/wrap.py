"""Explicit framework detection without monkey patching unknown objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import AdapterCapabilities, CapabilityLevel


@dataclass(frozen=True, slots=True)
class WrappedAgent:
    agent: Any
    capabilities: AdapterCapabilities


def wrap_agent(agent: Any) -> WrappedAgent:
    module = type(agent).__module__.lower()
    if "langgraph" in module:
        return WrappedAgent(
            agent,
            AdapterCapabilities(
                "langgraph",
                "1.x",
                CapabilityLevel.GRAPH,
                True,
                True,
                True,
                True,
                True,
                True,
                True,
                False,
                ("replay requires the core ReplayExecutor",),
            ),
        )
    if "langchain" in module:
        return WrappedAgent(
            agent,
            AdapterCapabilities(
                "langchain",
                "1.x",
                CapabilityLevel.ACTION,
                True,
                True,
                True,
                False,
                False,
                False,
                True,
                False,
            ),
        )
    if "autogen" in module:
        level = CapabilityLevel.ACTION
        return WrappedAgent(
            agent,
            AdapterCapabilities(
                "autogen-agentchat" if "agentchat" in module else "autogen-core",
                "0.7.x",
                level,
                True,
                True,
                True,
                False,
                False,
                False,
                False,
                False,
                ("event bridge integration is required for observation",),
            ),
        )
    if "crewai" in module:
        return WrappedAgent(
            agent,
            AdapterCapabilities(
                "crewai",
                "1.x",
                CapabilityLevel.RUN,
                True,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                ("use public event listeners; graph fidelity is not guaranteed",),
            ),
        )
    raise TypeError(
        f"unsupported agent framework: {type(agent).__module__}.{type(agent).__qualname__}"
    )
