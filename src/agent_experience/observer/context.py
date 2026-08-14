"""Context-local run and causation state for nested observations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObservationContext:
    """Identifiers propagated through synchronous and asynchronous calls."""

    run_id: str
    correlation_id: str
    causation_id: str = ""


_CURRENT: ContextVar[ObservationContext | None] = ContextVar(
    "agent_experience_observation_context",
    default=None,
)


def current_context() -> ObservationContext | None:
    """Return the active observation context, if one exists."""

    return _CURRENT.get()


def install_context(context: ObservationContext) -> Token[ObservationContext | None]:
    """Install a context until the returned token is reset."""

    return _CURRENT.set(context)


def reset_context(token: Token[ObservationContext | None]) -> None:
    """Restore the context associated with a previous install token."""

    _CURRENT.reset(token)


@contextmanager
def observation_context(context: ObservationContext) -> Iterator[None]:
    """Install a context for the duration of a nested operation."""

    token: Token[ObservationContext | None] = _CURRENT.set(context)
    try:
        yield
    finally:
        _CURRENT.reset(token)
