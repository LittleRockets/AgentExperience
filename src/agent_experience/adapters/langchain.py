"""LangChain 1.x middleware adapter loaded only when its extra is installed."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from contextvars import Token
from typing import Any

from agent_experience.observer.context import (
    ObservationContext,
    current_context,
    install_context,
    observation_context,
    reset_context,
)
from agent_experience.schema import events_pb2
from agent_experience.security import RedactionPolicy

from ._utils import get_value, object_summary
from .base import AdapterCapabilities, CapabilityLevel, EventSink

LANGCHAIN_CAPABILITIES = AdapterCapabilities(
    framework="langchain",
    integration_version="1.x",
    level=CapabilityLevel.ACTION,
    observes_runs=True,
    observes_models=True,
    observes_tools=True,
    supports_advice=False,
    supports_replay=False,
    supports_async=True,
    limitations=(
        "Outcome evaluation must be supplied by the application.",
        "Graph node and route events require the LangGraph adapter.",
    ),
)


def create_langchain_middleware(
    repository: EventSink,
    *,
    producer: str = "langchain",
    redaction: RedactionPolicy | None = None,
) -> object:
    """Create middleware without importing LangChain at core package import time."""

    try:
        from langchain.agents.middleware import AgentMiddleware
    except ImportError as error:
        raise ImportError(
            "LangChain support requires the optional dependency: "
            "pip install 'agent-experience[langchain]'"
        ) from error

    policy = redaction or RedactionPolicy()

    class AgentExperienceMiddleware(AgentMiddleware):
        """Record public LangChain agent, model, and tool lifecycle hooks."""

        capabilities = LANGCHAIN_CAPABILITIES

        def __init__(self) -> None:
            super().__init__()
            self._context_tokens: dict[str, Token[ObservationContext | None]] = {}
            self._context_lock = threading.Lock()

        def before_agent(self, state: Any, runtime: Any) -> None:
            run_id = _langchain_run_id(runtime)
            context = ObservationContext(run_id, run_id)
            token = _install_context(context)
            with self._context_lock:
                self._context_tokens[run_id] = token
            repository.append_event(
                events_pb2.RUN_STARTED,
                run_id=run_id,
                producer=producer,
                payload={"framework": "langchain", "state": object_summary(state, policy)},
            )

        def after_agent(self, state: Any, runtime: Any) -> None:
            context = current_context()
            run_id = context.run_id if context else _langchain_run_id(runtime)
            repository.append_event(
                events_pb2.RUN_COMPLETED,
                run_id=run_id,
                producer=producer,
                payload={"framework": "langchain", "state": object_summary(state, policy)},
            )
            with self._context_lock:
                token = self._context_tokens.pop(run_id, None)
            if token is not None:
                reset_context(token)

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            return _wrap_model(repository, producer, policy, request, handler)

        async def awrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            return await _awrap_model(repository, producer, policy, request, handler)

        def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            return _wrap_tool(repository, producer, policy, request, handler)

        async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            return await _awrap_tool(repository, producer, policy, request, handler)

    return AgentExperienceMiddleware()


def _langchain_run_id(runtime: object) -> str:
    for source in (runtime, get_value(runtime, "context"), get_value(runtime, "config")):
        value = get_value(source, "run_id") if source is not None else None
        if value:
            return str(value)
    return str(uuid.uuid4())


def _install_context(context: ObservationContext) -> Token[ObservationContext | None]:
    return install_context(context)


def _active_context() -> ObservationContext:
    context = current_context()
    if context is None:
        run_id = str(uuid.uuid4())
        return ObservationContext(run_id, run_id)
    return context


def _model_payload(request: object, policy: RedactionPolicy) -> dict[str, Any]:
    model = get_value(request, "model")
    return {
        "model": type(model).__name__ if model is not None else "unknown",
        "state": object_summary(get_value(request, "state"), policy),
    }


def _wrap_model(
    repository: EventSink,
    producer: str,
    policy: RedactionPolicy,
    request: object,
    handler: Callable[[Any], Any],
) -> Any:
    context = _active_context()
    payload = _model_payload(request, policy)
    started = repository.append_event(
        events_pb2.MODEL_CALL_STARTED,
        run_id=context.run_id,
        producer=producer,
        payload=payload,
        correlation_id=context.correlation_id,
        causation_id=context.causation_id,
    )
    begin = time.perf_counter_ns()
    try:
        with observation_context(
            ObservationContext(context.run_id, context.correlation_id, started.event_id)
        ):
            result = handler(request)
    except BaseException as error:
        _append_call_failure(
            repository,
            events_pb2.MODEL_CALL_FAILED,
            context,
            started.event_id,
            producer,
            payload,
            error,
            begin,
            policy,
        )
        raise
    _append_call_success(
        repository,
        events_pb2.MODEL_CALL_COMPLETED,
        context,
        started.event_id,
        producer,
        payload,
        result,
        begin,
        policy,
    )
    return result


async def _awrap_model(
    repository: EventSink,
    producer: str,
    policy: RedactionPolicy,
    request: object,
    handler: Callable[[Any], Any],
) -> Any:
    context = _active_context()
    payload = _model_payload(request, policy)
    started = repository.append_event(
        events_pb2.MODEL_CALL_STARTED,
        run_id=context.run_id,
        producer=producer,
        payload=payload,
        correlation_id=context.correlation_id,
        causation_id=context.causation_id,
    )
    begin = time.perf_counter_ns()
    try:
        with observation_context(
            ObservationContext(context.run_id, context.correlation_id, started.event_id)
        ):
            result = await handler(request)
    except BaseException as error:
        _append_call_failure(
            repository,
            events_pb2.MODEL_CALL_FAILED,
            context,
            started.event_id,
            producer,
            payload,
            error,
            begin,
            policy,
        )
        raise
    _append_call_success(
        repository,
        events_pb2.MODEL_CALL_COMPLETED,
        context,
        started.event_id,
        producer,
        payload,
        result,
        begin,
        policy,
    )
    return result


def _tool_payload(request: object, policy: RedactionPolicy) -> dict[str, Any]:
    call = get_value(request, "tool_call", {})
    tool = get_value(request, "tool")
    return {
        "tool_call_id": str(get_value(call, "id", uuid.uuid4())),
        "tool_name": str(get_value(call, "name", get_value(tool, "name", "unknown"))),
        "contract_id": str(get_value(tool, "name", "unknown")),
        "args": policy.sanitize(get_value(call, "args", {})),
    }


def _wrap_tool(
    repository: EventSink,
    producer: str,
    policy: RedactionPolicy,
    request: object,
    handler: Callable[[Any], Any],
) -> Any:
    context = _active_context()
    payload = _tool_payload(request, policy)
    started = repository.append_event(
        events_pb2.TOOL_CALL_STARTED,
        run_id=context.run_id,
        producer=producer,
        payload=payload,
        correlation_id=context.correlation_id,
        causation_id=context.causation_id,
    )
    begin = time.perf_counter_ns()
    try:
        with observation_context(
            ObservationContext(context.run_id, context.correlation_id, started.event_id)
        ):
            result = handler(request)
    except BaseException as error:
        _append_call_failure(
            repository,
            events_pb2.TOOL_CALL_FAILED,
            context,
            started.event_id,
            producer,
            payload,
            error,
            begin,
            policy,
        )
        raise
    _append_call_success(
        repository,
        events_pb2.TOOL_CALL_COMPLETED,
        context,
        started.event_id,
        producer,
        payload,
        result,
        begin,
        policy,
    )
    return result


async def _awrap_tool(
    repository: EventSink,
    producer: str,
    policy: RedactionPolicy,
    request: object,
    handler: Callable[[Any], Any],
) -> Any:
    context = _active_context()
    payload = _tool_payload(request, policy)
    started = repository.append_event(
        events_pb2.TOOL_CALL_STARTED,
        run_id=context.run_id,
        producer=producer,
        payload=payload,
        correlation_id=context.correlation_id,
        causation_id=context.causation_id,
    )
    begin = time.perf_counter_ns()
    try:
        with observation_context(
            ObservationContext(context.run_id, context.correlation_id, started.event_id)
        ):
            result = await handler(request)
    except BaseException as error:
        _append_call_failure(
            repository,
            events_pb2.TOOL_CALL_FAILED,
            context,
            started.event_id,
            producer,
            payload,
            error,
            begin,
            policy,
        )
        raise
    _append_call_success(
        repository,
        events_pb2.TOOL_CALL_COMPLETED,
        context,
        started.event_id,
        producer,
        payload,
        result,
        begin,
        policy,
    )
    return result


def _append_call_success(
    repository: EventSink,
    event_type: int,
    context: ObservationContext,
    causation_id: str,
    producer: str,
    payload: dict[str, Any],
    result: object,
    begin: int,
    policy: RedactionPolicy,
) -> None:
    repository.append_event(
        event_type,
        run_id=context.run_id,
        producer=producer,
        payload={
            **payload,
            "result": object_summary(result, policy),
            "duration_ns": time.perf_counter_ns() - begin,
        },
        correlation_id=context.correlation_id,
        causation_id=causation_id,
    )


def _append_call_failure(
    repository: EventSink,
    event_type: int,
    context: ObservationContext,
    causation_id: str,
    producer: str,
    payload: dict[str, Any],
    error: BaseException,
    begin: int,
    policy: RedactionPolicy,
) -> None:
    repository.append_event(
        event_type,
        run_id=context.run_id,
        producer=producer,
        payload={
            **payload,
            "error_type": type(error).__name__,
            "error": policy.sanitize(str(error)),
            "duration_ns": time.perf_counter_ns() - begin,
        },
        correlation_id=context.correlation_id,
        causation_id=causation_id,
    )
