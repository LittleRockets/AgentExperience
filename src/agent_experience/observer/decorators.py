"""Run-level observation for ordinary synchronous and asynchronous Python functions."""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast

from agent_experience.outcome import OutcomeEvaluator
from agent_experience.schema import events_pb2
from agent_experience.security import RedactionPolicy
from agent_experience.storage.repository import Repository

from .context import ObservationContext, observation_context

P = ParamSpec("P")
R = TypeVar("R")


def capture(
    repository: Repository,
    *,
    producer: str = "generic-python",
    evaluator: OutcomeEvaluator[R] | None = None,
    redaction: RedactionPolicy | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Capture function Run boundaries without changing its return or exception semantics."""

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        policy = redaction or RedactionPolicy()

        def started_payload(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
            return {
                "callable": function.__qualname__,
                "args": policy.sanitize(args),
                "kwargs": policy.sanitize(kwargs),
            }

        def evaluate(run_id: str, result: R, causation_id: str) -> None:
            if evaluator is None:
                return
            evaluation = evaluator.evaluate(result)
            repository.append_event(
                events_pb2.OUTCOME_EVALUATED,
                run_id=run_id,
                producer=producer,
                payload={
                    "outcome": evaluation.outcome.value,
                    "confidence": evaluation.confidence,
                    "evaluator_id": evaluation.evaluator_id,
                    "evaluator_version": evaluation.evaluator_version,
                    "evidence": list(evaluation.evidence),
                },
                correlation_id=run_id,
                causation_id=causation_id,
            )

        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                run_id = str(uuid.uuid4())
                started = time.perf_counter_ns()
                started_event = repository.append_event(
                    events_pb2.RUN_STARTED,
                    run_id=run_id,
                    producer=producer,
                    payload=started_payload(args, kwargs),
                )
                try:
                    context = ObservationContext(run_id, run_id, started_event.event_id)
                    with observation_context(context):
                        result = await function(*args, **kwargs)
                except BaseException as error:
                    repository.append_event(
                        events_pb2.RUN_FAILED,
                        run_id=run_id,
                        producer=producer,
                        payload={
                            "error_type": type(error).__name__,
                            "error": policy.sanitize(str(error)),
                            "duration_ns": time.perf_counter_ns() - started,
                        },
                    )
                    raise
                completed_event = repository.append_event(
                    events_pb2.RUN_COMPLETED,
                    run_id=run_id,
                    producer=producer,
                    payload={
                        "result": policy.sanitize(result),
                        "duration_ns": time.perf_counter_ns() - started,
                    },
                )
                evaluate(run_id, result, completed_event.event_id)
                return result

            return cast(Callable[P, R], async_wrapper)

        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            run_id = str(uuid.uuid4())
            started = time.perf_counter_ns()
            started_event = repository.append_event(
                events_pb2.RUN_STARTED,
                run_id=run_id,
                producer=producer,
                payload=started_payload(args, kwargs),
            )
            try:
                context = ObservationContext(run_id, run_id, started_event.event_id)
                with observation_context(context):
                    result = function(*args, **kwargs)
            except BaseException as error:
                repository.append_event(
                    events_pb2.RUN_FAILED,
                    run_id=run_id,
                    producer=producer,
                    payload={
                        "error_type": type(error).__name__,
                        "error": policy.sanitize(str(error)),
                        "duration_ns": time.perf_counter_ns() - started,
                    },
                )
                raise
            completed_event = repository.append_event(
                events_pb2.RUN_COMPLETED,
                run_id=run_id,
                producer=producer,
                payload={
                    "result": policy.sanitize(result),
                    "duration_ns": time.perf_counter_ns() - started,
                },
            )
            evaluate(run_id, result, completed_event.event_id)
            return result

        return wrapper

    return decorate
