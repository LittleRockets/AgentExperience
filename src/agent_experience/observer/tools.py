"""Explicit tool contracts for generic Python observation."""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_experience.schema import events_pb2
from agent_experience.security import RedactionPolicy
from agent_experience.storage.repository import Repository

from .context import ObservationContext, current_context, observation_context


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Stable identity and safety metadata for an observed tool."""

    contract_id: str
    name: str
    function: Callable[..., Any]
    version: str = ""
    idempotent: bool = False
    has_external_side_effects: bool = True


class ToolRegistry:
    """In-process allowlist of explicitly registered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """Register a unique tool contract."""

        if not spec.contract_id:
            raise ValueError("tool contract_id must not be empty")
        if spec.contract_id in self._tools:
            raise ValueError(f"tool already registered: {spec.contract_id}")
        self._tools[spec.contract_id] = spec

    def get(self, contract_id: str) -> ToolSpec:
        """Resolve a registered tool contract or raise KeyError."""

        return self._tools[contract_id]

    def list(self) -> tuple[ToolSpec, ...]:
        """Return registered tools in deterministic contract-ID order."""

        return tuple(self._tools[key] for key in sorted(self._tools))

    def observed(
        self,
        contract_id: str,
        repository: Repository,
        *,
        producer: str = "generic-tool",
        redaction: RedactionPolicy | None = None,
    ) -> Callable[..., Any]:
        """Return a callable that records the registered tool's complete lifecycle."""

        spec = self.get(contract_id)
        policy = redaction or RedactionPolicy()

        def event_payload(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
            return {
                "tool_call_id": str(uuid.uuid4()),
                "contract_id": spec.contract_id,
                "tool_name": spec.name,
                "tool_version": spec.version,
                "idempotent": spec.idempotent,
                "has_external_side_effects": spec.has_external_side_effects,
                "args": policy.sanitize(args),
                "kwargs": policy.sanitize(kwargs),
            }

        if inspect.iscoroutinefunction(spec.function):

            @functools.wraps(spec.function)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await _invoke_async(
                    spec.function,
                    args,
                    kwargs,
                    event_payload(args, kwargs),
                    repository,
                    producer,
                    policy,
                )

            return async_wrapper

        @functools.wraps(spec.function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _invoke_sync(
                spec.function,
                args,
                kwargs,
                event_payload(args, kwargs),
                repository,
                producer,
                policy,
            )

        return wrapper


def _required_context() -> ObservationContext:
    context = current_context()
    if context is None:
        raise RuntimeError("observed tools must run inside an AgentExperience capture context")
    return context


def _start_tool(
    payload: dict[str, Any], repository: Repository, producer: str
) -> tuple[ObservationContext, str, int]:
    context = _required_context()
    event = repository.append_event(
        events_pb2.TOOL_CALL_STARTED,
        run_id=context.run_id,
        producer=producer,
        payload=payload,
        correlation_id=context.correlation_id,
        causation_id=context.causation_id,
    )
    return context, event.event_id, time.perf_counter_ns()


def _finish_payload(base: dict[str, Any], started: int, **values: Any) -> dict[str, Any]:
    return {**base, "duration_ns": time.perf_counter_ns() - started, **values}


def _invoke_sync(
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    payload: dict[str, Any],
    repository: Repository,
    producer: str,
    policy: RedactionPolicy,
) -> Any:
    context, started_event_id, started = _start_tool(payload, repository, producer)
    nested = ObservationContext(context.run_id, context.correlation_id, started_event_id)
    try:
        with observation_context(nested):
            result = function(*args, **kwargs)
    except BaseException as error:
        repository.append_event(
            events_pb2.TOOL_CALL_FAILED,
            run_id=context.run_id,
            producer=producer,
            payload=_finish_payload(
                payload,
                started,
                error_type=type(error).__name__,
                error=policy.sanitize(str(error)),
            ),
            correlation_id=context.correlation_id,
            causation_id=started_event_id,
        )
        raise
    repository.append_event(
        events_pb2.TOOL_CALL_COMPLETED,
        run_id=context.run_id,
        producer=producer,
        payload=_finish_payload(payload, started, result=policy.sanitize(result)),
        correlation_id=context.correlation_id,
        causation_id=started_event_id,
    )
    return result


async def _invoke_async(
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    payload: dict[str, Any],
    repository: Repository,
    producer: str,
    policy: RedactionPolicy,
) -> Any:
    context, started_event_id, started = _start_tool(payload, repository, producer)
    nested = ObservationContext(context.run_id, context.correlation_id, started_event_id)
    try:
        with observation_context(nested):
            result = await function(*args, **kwargs)
    except BaseException as error:
        repository.append_event(
            events_pb2.TOOL_CALL_FAILED,
            run_id=context.run_id,
            producer=producer,
            payload=_finish_payload(
                payload,
                started,
                error_type=type(error).__name__,
                error=policy.sanitize(str(error)),
            ),
            correlation_id=context.correlation_id,
            causation_id=started_event_id,
        )
        raise
    repository.append_event(
        events_pb2.TOOL_CALL_COMPLETED,
        run_id=context.run_id,
        producer=producer,
        payload=_finish_payload(payload, started, result=policy.sanitize(result)),
        correlation_id=context.correlation_id,
        causation_id=started_event_id,
    )
    return result
