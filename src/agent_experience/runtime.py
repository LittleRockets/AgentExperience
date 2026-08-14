"""Decorator-first runtime: the primary AgentExperience API."""

from __future__ import annotations

import atexit
import functools
import hashlib
import inspect
import queue
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast, overload

from agent_experience.experience import CandidateService
from agent_experience.observer.context import (
    ObservationContext,
    current_context,
    observation_context,
)
from agent_experience.package import (
    CapabilityCatalog,
    MountPolicy,
    MountReport,
    PackageInspection,
    PackageService,
    PackageSigner,
    PackageSource,
    TrustStore,
)
from agent_experience.schema import events_pb2
from agent_experience.security import RedactionPolicy
from agent_experience.storage import Repository

P = ParamSpec("P")
R = TypeVar("R")
_STOP = object()


class InstrumentationGateway:
    """The only event-writing surface exposed to framework adapters."""

    def __init__(self, runtime: ExperienceRuntime) -> None:
        self.runtime = runtime

    def append_event(self, event_type: int, **kwargs: Any) -> events_pb2.EventEnvelope:
        return self.runtime.repository.append_event(event_type, **kwargs)


class ExperienceRuntime:
    """Own observation, identity, storage and consolidation behind two decorators."""

    def __init__(
        self,
        path: str | Path = ".agent-experience",
        *,
        redaction: RedactionPolicy | None = None,
        minimum_confidence: float = 0.8,
        experiences: Iterable[str | Path] = (),
        mount_policy: MountPolicy | None = None,
        package_source: PackageSource | None = None,
    ) -> None:
        self.path = Path(path)
        self.redaction = redaction or RedactionPolicy()
        self.minimum_confidence = minimum_confidence
        self.mount_policy = mount_policy or MountPolicy()
        self.package_source = package_source
        self._repository: Repository | None = None
        self._repository_lock = threading.RLock()
        self._jobs: queue.Queue[object] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._worker_error: BaseException | None = None
        self._closed = False
        self._gateway = InstrumentationGateway(self)
        self._capabilities = CapabilityCatalog()
        self._frameworks: set[str] = set()
        self._pending_experiences = list(experiences)
        atexit.register(self.close)

    @property
    def repository(self) -> Repository:
        """Expose the owned repository for inspection, export and advanced APIs."""

        with self._repository_lock:
            if self._closed:
                raise RuntimeError("ExperienceRuntime is closed")
            if self._repository is None:
                self._repository = Repository(self.path)
            return self._repository

    @overload
    def run(self, function: Callable[P, R]) -> Callable[P, R]: ...

    @overload
    def run(
        self, *, verify: Callable[[R], bool] | None = None
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...

    def run(
        self,
        function: Callable[P, R] | None = None,
        *,
        verify: Callable[[R], bool] | None = None,
    ) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
        """Observe an agent/chain boundary, optionally verifying its business outcome."""

        def decorate(target: Callable[P, R]) -> Callable[P, R]:
            identity = _callable_identity(target, "run")
            if inspect.iscoroutinefunction(target):

                @functools.wraps(target)
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                    return await self._run_async(target, identity, verify, args, kwargs)

                return cast(Callable[P, R], async_wrapper)

            @functools.wraps(target)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                return self._run_sync(target, identity, verify, args, kwargs)

            return wrapper

        return decorate(function) if function is not None else decorate

    @overload
    def tool(self, function: Callable[P, R]) -> Callable[P, R]: ...

    @overload
    def tool(self, *, capability: str = "") -> Callable[[Callable[P, R]], Callable[P, R]]: ...

    def tool(
        self,
        function: Callable[P, R] | None = None,
        *,
        capability: str = "",
    ) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
        """Observe a Python tool with an automatically generated stable identity."""

        def decorate(target: Callable[P, R]) -> Callable[P, R]:
            return self._decorate_tool(target, capability)

        return decorate(function) if function is not None else decorate

    def _decorate_tool(self, function: Callable[P, R], capability: str) -> Callable[P, R]:
        """Create one tool wrapper and register its portable capability."""

        identity = _callable_identity(function, "tool")
        self._capabilities.register_callable(function, identity, capability=capability)
        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                if current_context() is None:
                    return await self._standalone_tool_async(function, identity, args, kwargs)
                return await self._tool_async(function, identity, args, kwargs)

            return cast(Callable[P, R], async_wrapper)

        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if current_context() is None:
                return self._standalone_tool_sync(function, identity, args, kwargs)
            return self._tool_sync(function, identity, args, kwargs)

        return wrapper

    def langchain(self) -> object:
        """Return LangChain middleware bound to this Runtime's gateway."""

        from agent_experience.adapters import create_langchain_middleware

        self._frameworks.add("langchain")
        return create_langchain_middleware(self._gateway, redaction=self.redaction)

    def langgraph(self, *, run_id: str | None = None) -> Any:
        """Return a LangGraph event bridge bound to this Runtime's gateway."""

        from agent_experience.adapters import LangGraphEventBridge

        self._frameworks.add("langgraph")
        return LangGraphEventBridge(
            self._gateway,
            run_id=run_id,
            redaction=self.redaction,
        )

    def mcp(
        self,
        session: Any,
        *,
        trust_domain: str,
        transport_identity: str = "",
    ) -> Any:
        """Return an MCP client proxy bound to this Runtime's gateway."""

        from agent_experience.adapters import ObservedClientSession

        self._frameworks.add("mcp")
        return ObservedClientSession(
            session,
            self._gateway,
            trust_domain=trust_domain,
            transport_identity=transport_identity,
            redaction=self.redaction,
        )

    def inspect_package(self, reference: str | Path, *, sha256: str = "") -> PackageInspection:
        """Inspect a local/HTTPS package without mutating the mount catalog."""

        return self._package_service().inspect(reference, sha256=sha256)

    @property
    def trust(self) -> TrustStore:
        """Repository-local trusted package signing keys."""

        return self._package_service().trust_store

    def mount(
        self,
        reference: str | Path,
        *,
        sha256: str = "",
        bindings: dict[str, str] | None = None,
    ) -> MountReport:
        """Safely mount one package in quarantine and return a complete report."""

        return self._package_service().mount(reference, sha256=sha256, bindings=bindings)

    def mounts(self) -> tuple[MountReport, ...]:
        """Return current mounted-package states."""

        self._ensure_pending_mounts()
        return self._package_service().mounts()

    def validate_mount(
        self,
        package_name: str,
        verifier: Callable[[Any], bool],
        *,
        max_runs: int = 6,
    ) -> MountReport:
        """Apply bounded caller-controlled local validation to a quarantined mount."""

        return self._package_service().validate_mount(package_name, verifier, max_runs=max_runs)

    def upgrade_mount(
        self, package_name: str, reference: str | Path, *, sha256: str = ""
    ) -> MountReport:
        """Mount a new immutable package generation without disrupting the old one."""

        return self._package_service().upgrade(package_name, reference, sha256=sha256)

    def rollback_mount(self, package_name: str) -> MountReport:
        """Move the mount view back to its previous recorded generation."""

        return self._package_service().rollback(package_name)

    def unmount(self, package_name: str) -> MountReport:
        """Disable a mounted package while preserving its audit trail."""

        return self._package_service().unmount(package_name)

    def export(
        self,
        destination: str | Path,
        *,
        name: str,
        version: str,
        publisher: str = "",
        signer: PackageSigner | None = None,
    ) -> Path:
        """Export validated/active experience as a self-describing v2 package."""

        return self._package_service().export(
            destination,
            name=name,
            version=version,
            publisher=publisher,
            signer=signer,
        )

    def flush(self) -> None:
        """Wait for queued candidate consolidation and surface worker errors."""

        self._ensure_pending_mounts()
        self._jobs.join()
        if self._worker_error is not None:
            error = self._worker_error
            self._worker_error = None
            raise RuntimeError("experience consolidation failed") from error

    def close(self) -> None:
        """Flush, stop the worker and close storage; safe to call repeatedly."""

        with self._repository_lock:
            if self._closed:
                return
        self.flush()
        with self._repository_lock:
            if self._worker is not None:
                self._jobs.put(_STOP)
                self._jobs.join()
                self._worker.join(timeout=5)
            if self._repository is not None:
                self._repository.close()
            self._closed = True

    def __enter__(self) -> ExperienceRuntime:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _run_sync(
        self,
        function: Callable[P, R],
        identity: str,
        verify: Callable[[R], bool] | None,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> R:
        run_id, started_ns, started_event_id = self._start_run(identity, args, kwargs)
        try:
            with observation_context(ObservationContext(run_id, run_id, started_event_id)):
                result = function(*args, **kwargs)
        except BaseException as error:
            self._fail_run(run_id, identity, started_ns, error)
            raise
        self._complete_run(run_id, identity, started_ns, result, verify)
        return result

    async def _run_async(
        self,
        function: Callable[..., Any],
        identity: str,
        verify: Callable[[Any], bool] | None,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        run_id, started_ns, started_event_id = self._start_run(identity, args, kwargs)
        try:
            with observation_context(ObservationContext(run_id, run_id, started_event_id)):
                result = await function(*args, **kwargs)
        except BaseException as error:
            self._fail_run(run_id, identity, started_ns, error)
            raise
        self._complete_run(run_id, identity, started_ns, result, verify)
        return result

    def _standalone_tool_sync(
        self,
        function: Callable[P, R],
        identity: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> R:
        return self._run_sync(
            lambda *call_args, **call_kwargs: self._tool_sync(
                function, identity, call_args, call_kwargs
            ),
            f"standalone:{identity}",
            None,
            args,
            kwargs,
        )

    async def _standalone_tool_async(
        self,
        function: Callable[..., Any],
        identity: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        async def invoke(*call_args: Any, **call_kwargs: Any) -> Any:
            return await self._tool_async(function, identity, call_args, call_kwargs)

        return await self._run_async(invoke, f"standalone:{identity}", None, args, kwargs)

    def _tool_sync(
        self,
        function: Callable[P, R],
        identity: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> R:
        context, started_ns, started_id, payload = self._start_tool(identity, args, kwargs)
        try:
            with observation_context(
                ObservationContext(context.run_id, context.correlation_id, started_id)
            ):
                result = function(*args, **kwargs)
        except BaseException as error:
            self._finish_tool(
                events_pb2.TOOL_CALL_FAILED,
                context,
                started_id,
                started_ns,
                payload,
                error=error,
            )
            raise
        self._finish_tool(
            events_pb2.TOOL_CALL_COMPLETED,
            context,
            started_id,
            started_ns,
            payload,
            result=result,
        )
        return result

    async def _tool_async(
        self,
        function: Callable[..., Any],
        identity: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        context, started_ns, started_id, payload = self._start_tool(identity, args, kwargs)
        try:
            with observation_context(
                ObservationContext(context.run_id, context.correlation_id, started_id)
            ):
                result = await function(*args, **kwargs)
        except BaseException as error:
            self._finish_tool(
                events_pb2.TOOL_CALL_FAILED,
                context,
                started_id,
                started_ns,
                payload,
                error=error,
            )
            raise
        self._finish_tool(
            events_pb2.TOOL_CALL_COMPLETED,
            context,
            started_id,
            started_ns,
            payload,
            result=result,
        )
        return result

    def _start_run(
        self, identity: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[str, int, str]:
        self._ensure_pending_mounts()
        run_id = str(uuid.uuid4())
        event = self.repository.append_event(
            events_pb2.RUN_STARTED,
            run_id=run_id,
            producer="agent-experience-runtime/v2",
            payload={
                "identity": identity,
                "args": self.redaction.sanitize(args),
                "kwargs": self.redaction.sanitize(kwargs),
            },
        )
        return run_id, time.perf_counter_ns(), event.event_id

    def _complete_run(
        self,
        run_id: str,
        identity: str,
        started_ns: int,
        result: R,
        verify: Callable[[R], bool] | None,
    ) -> None:
        completed = self.repository.append_event(
            events_pb2.RUN_COMPLETED,
            run_id=run_id,
            producer="agent-experience-runtime/v2",
            payload={
                "identity": identity,
                "result": self.redaction.sanitize(result),
                "duration_ns": time.perf_counter_ns() - started_ns,
            },
        )
        if verify is None:
            return
        passed = bool(verify(result))
        self.repository.append_event(
            events_pb2.OUTCOME_EVALUATED,
            run_id=run_id,
            producer="agent-experience-runtime/v2",
            payload={
                "outcome": "success" if passed else "failure",
                "confidence": 1.0,
                "evaluator_id": f"runtime-verifier:{identity}",
                "evaluator_version": "1",
                "evidence": [
                    "run boundary verifier returned true"
                    if passed
                    else "run boundary verifier returned false"
                ],
            },
            correlation_id=run_id,
            causation_id=completed.event_id,
        )
        if passed:
            self._enqueue_consolidation()

    def _fail_run(self, run_id: str, identity: str, started_ns: int, error: BaseException) -> None:
        self.repository.append_event(
            events_pb2.RUN_FAILED,
            run_id=run_id,
            producer="agent-experience-runtime/v2",
            payload={
                "identity": identity,
                "error_type": type(error).__name__,
                "error": self.redaction.sanitize(str(error)),
                "duration_ns": time.perf_counter_ns() - started_ns,
            },
        )

    def _start_tool(
        self, identity: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[ObservationContext, int, str, dict[str, Any]]:
        context = current_context()
        if context is None:
            raise RuntimeError("tool observation requires a runtime run context")
        payload = {
            "tool_call_id": str(uuid.uuid4()),
            "contract_id": identity,
            "tool_name": identity,
            "args": self.redaction.sanitize(args),
            "kwargs": self.redaction.sanitize(kwargs),
            "idempotent": False,
            "has_external_side_effects": True,
        }
        event = self.repository.append_event(
            events_pb2.TOOL_CALL_STARTED,
            run_id=context.run_id,
            producer="agent-experience-runtime/v2",
            payload=payload,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
        )
        return context, time.perf_counter_ns(), event.event_id, payload

    def _finish_tool(
        self,
        event_type: int,
        context: ObservationContext,
        started_id: str,
        started_ns: int,
        payload: dict[str, Any],
        *,
        result: Any = None,
        error: BaseException | None = None,
    ) -> None:
        values = dict(payload)
        values["duration_ns"] = time.perf_counter_ns() - started_ns
        if error is None:
            values["result"] = self.redaction.sanitize(result)
        else:
            values["error_type"] = type(error).__name__
            values["error"] = self.redaction.sanitize(str(error))
        self.repository.append_event(
            event_type,
            run_id=context.run_id,
            producer="agent-experience-runtime/v2",
            payload=values,
            correlation_id=context.correlation_id,
            causation_id=started_id,
        )

    def _enqueue_consolidation(self) -> None:
        with self._repository_lock:
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._consolidation_worker,
                    name="agent-experience-consolidation",
                    daemon=True,
                )
                self._worker.start()
            self._jobs.put("extract")

    def _consolidation_worker(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                if job is _STOP:
                    return
                CandidateService(
                    self.repository, minimum_confidence=self.minimum_confidence
                ).extract_all()
            except BaseException as error:
                self._worker_error = error
            finally:
                self._jobs.task_done()

    def _package_service(self) -> PackageService:
        return PackageService(
            self.repository,
            capabilities=self._capabilities,
            frameworks=frozenset(self._frameworks),
            policy=self.mount_policy,
            source=self.package_source,
        )

    def _ensure_pending_mounts(self) -> None:
        if not self._pending_experiences:
            return
        pending, self._pending_experiences = self._pending_experiences, []
        try:
            for reference in pending:
                self.mount(reference)
        except BaseException:
            self._pending_experiences = pending
            raise


def agent_experience(
    path: str | Path = ".agent-experience",
    *,
    redaction: RedactionPolicy | None = None,
    minimum_confidence: float = 0.8,
    experiences: Iterable[str | Path] = (),
    mount_policy: MountPolicy | None = None,
    package_source: PackageSource | None = None,
) -> ExperienceRuntime:
    """Create the single path-scoped runtime used by run/tool decorators."""

    return ExperienceRuntime(
        path,
        redaction=redaction,
        minimum_confidence=minimum_confidence,
        experiences=experiences,
        mount_policy=mount_policy,
        package_source=package_source,
    )


def _callable_identity(function: Callable[..., Any], kind: str) -> str:
    try:
        signature = str(inspect.signature(function))
    except (TypeError, ValueError):
        signature = "(?)"
    code = getattr(function, "__code__", None)
    material = "\x1f".join(
        (
            kind,
            function.__module__,
            function.__qualname__,
            signature,
            code.co_code.hex() if code is not None else type(function).__qualname__,
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"python://{function.__module__}.{function.__qualname__}@{digest}"
