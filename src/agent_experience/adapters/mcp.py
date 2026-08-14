"""Transport-independent observation proxy for MCP Python client sessions."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from agent_experience.observer.context import current_context
from agent_experience.schema import events_pb2
from agent_experience.security import RedactionPolicy

from ._utils import get_value, object_summary
from .base import AdapterCapabilities, CapabilityLevel, EventSink

MCP_CAPABILITIES = AdapterCapabilities(
    framework="mcp",
    integration_version="1.x",
    level=CapabilityLevel.ACTION,
    observes_runs=False,
    observes_tools=True,
    limitations=(
        "Resources and rendered prompts are recorded as identities and hashes, not raw content.",
        "Session notification callbacks require host integration and are not intercepted "
        "by proxying.",
    ),
)


@dataclass(frozen=True, slots=True)
class MCPServerIdentity:
    """Stable identity inputs for one trusted MCP server connection."""

    trust_domain: str
    server_name: str
    server_version: str = ""
    transport_identity: str = ""

    @property
    def canonical_id(self) -> str:
        material = "\x1f".join(
            (self.trust_domain, self.server_name, self.server_version, self.transport_identity)
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        return f"mcp://{self.trust_domain}/{self.server_name}@{digest}"


class ClientSessionLike(Protocol):
    async def initialize(self, *args: Any, **kwargs: Any) -> Any: ...

    async def list_tools(self, *args: Any, **kwargs: Any) -> Any: ...

    async def list_resources(self, *args: Any, **kwargs: Any) -> Any: ...

    async def list_resource_templates(self, *args: Any, **kwargs: Any) -> Any: ...

    async def list_prompts(self, *args: Any, **kwargs: Any) -> Any: ...

    async def call_tool(self, name: str, arguments: Any, *args: Any, **kwargs: Any) -> Any: ...

    async def read_resource(self, uri: str, *args: Any, **kwargs: Any) -> Any: ...

    async def get_prompt(self, name: str, arguments: Any, *args: Any, **kwargs: Any) -> Any: ...


class ObservedClientSession:
    """Proxy public MCP ClientSession operations while preserving return and error semantics."""

    capabilities = MCP_CAPABILITIES

    def __init__(
        self,
        session: ClientSessionLike,
        repository: EventSink,
        *,
        trust_domain: str,
        transport_identity: str = "",
        producer: str = "mcp-client",
        redaction: RedactionPolicy | None = None,
    ) -> None:
        if not trust_domain:
            raise ValueError("MCP trust_domain must not be empty")
        self.session = session
        self.repository = repository
        self.trust_domain = trust_domain
        self.transport_identity = transport_identity
        self.producer = producer
        self.policy = redaction or RedactionPolicy()
        self.identity = MCPServerIdentity(
            trust_domain, "uninitialized", transport_identity=transport_identity
        )
        self.session_run_id = str(uuid.uuid4())

    def __getattr__(self, name: str) -> Any:
        return getattr(self.session, name)

    async def initialize(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.session.initialize(*args, **kwargs)
        server_info = get_value(result, "server_info", get_value(result, "serverInfo"))
        self.identity = MCPServerIdentity(
            self.trust_domain,
            str(get_value(server_info, "name", "unknown")),
            str(get_value(server_info, "version", "")),
            self.transport_identity,
        )
        self._append(
            events_pb2.MCP_SESSION_INITIALIZED,
            {
                "server_id": self.identity.canonical_id,
                "server_name": self.identity.server_name,
                "server_version": self.identity.server_version,
                "protocol_version": str(
                    get_value(result, "protocol_version", get_value(result, "protocolVersion", ""))
                ),
                "capabilities": object_summary(get_value(result, "capabilities"), self.policy),
            },
        )
        return result

    async def list_tools(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.session.list_tools(*args, **kwargs)
        tools = get_value(result, "tools", ()) or ()
        entries = [self._tool_definition(tool) for tool in tools]
        self._capability_snapshot(
            "tools", entries, get_value(result, "next_cursor", get_value(result, "nextCursor"))
        )
        return result

    async def list_resources(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.session.list_resources(*args, **kwargs)
        resources = get_value(result, "resources", ()) or ()
        entries = [self._resource_definition(resource) for resource in resources]
        self._capability_snapshot(
            "resources", entries, get_value(result, "next_cursor", get_value(result, "nextCursor"))
        )
        return result

    async def list_resource_templates(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.session.list_resource_templates(*args, **kwargs)
        templates = get_value(result, "resource_templates", ()) or ()
        entries = [self._resource_definition(template) for template in templates]
        self._capability_snapshot(
            "resource_templates",
            entries,
            get_value(result, "next_cursor", get_value(result, "nextCursor")),
        )
        return result

    async def list_prompts(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.session.list_prompts(*args, **kwargs)
        prompts = get_value(result, "prompts", ()) or ()
        entries = [self._prompt_definition(prompt) for prompt in prompts]
        self._capability_snapshot(
            "prompts", entries, get_value(result, "next_cursor", get_value(result, "nextCursor"))
        )
        return result

    async def call_tool(
        self, name: str, arguments: Mapping[str, Any] | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        context = current_context()
        run_id = context.run_id if context else self.session_run_id
        correlation_id = context.correlation_id if context else run_id
        tool_call_id = str(uuid.uuid4())
        payload = {
            "tool_call_id": tool_call_id,
            "contract_id": self.tool_contract_id(name),
            "tool_name": name,
            "server_id": self.identity.canonical_id,
            "args": self.policy.sanitize(dict(arguments or {})),
        }
        started = self.repository.append_event(
            events_pb2.TOOL_CALL_STARTED,
            run_id=run_id,
            producer=self.producer,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=context.causation_id if context else "",
        )
        begin = time.perf_counter_ns()
        try:
            result = await self.session.call_tool(name, arguments, *args, **kwargs)
        except BaseException as error:
            self._append_tool_result(
                events_pb2.TOOL_CALL_FAILED,
                run_id,
                correlation_id,
                started.event_id,
                payload,
                begin,
                error=error,
            )
            raise
        is_error = bool(get_value(result, "is_error", get_value(result, "isError", False)))
        self._append_tool_result(
            events_pb2.TOOL_CALL_FAILED if is_error else events_pb2.TOOL_CALL_COMPLETED,
            run_id,
            correlation_id,
            started.event_id,
            payload,
            begin,
            result=result,
            protocol_error=is_error,
        )
        return result

    async def read_resource(self, uri: str, *args: Any, **kwargs: Any) -> Any:
        result = await self.session.read_resource(uri, *args, **kwargs)
        contents = get_value(result, "contents", ()) or ()
        hashes = [self._content_fingerprint(content) for content in contents]
        self._append(
            events_pb2.MCP_RESOURCE_READ,
            {
                "server_id": self.identity.canonical_id,
                "uri": str(uri),
                "content_count": len(hashes),
                "contents": hashes,
            },
        )
        return result

    async def get_prompt(
        self, name: str, arguments: Mapping[str, str] | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        result = await self.session.get_prompt(name, arguments, *args, **kwargs)
        messages = get_value(result, "messages", ()) or ()
        fingerprints = [self._content_fingerprint(message) for message in messages]
        self._append(
            events_pb2.MCP_PROMPT_RENDERED,
            {
                "server_id": self.identity.canonical_id,
                "prompt_id": self.prompt_contract_id(name),
                "prompt_name": name,
                "arguments": self.policy.sanitize(dict(arguments or {})),
                "message_count": len(fingerprints),
                "messages": fingerprints,
            },
        )
        return result

    def tool_contract_id(self, name: str, schema: object | None = None) -> str:
        schema_hash = _canonical_hash(schema)[:24] if schema is not None else "unknown-schema"
        return f"{self.identity.canonical_id}/tools/{name}@{schema_hash}"

    def prompt_contract_id(self, name: str) -> str:
        return f"{self.identity.canonical_id}/prompts/{name}"

    def _tool_definition(self, tool: object) -> dict[str, Any]:
        schema = get_value(tool, "input_schema", get_value(tool, "inputSchema", {}))
        name = str(get_value(tool, "name", "unknown"))
        return {
            "id": self.tool_contract_id(name, schema),
            "name": name,
            "title": str(get_value(tool, "title", "")),
            "description_hash": _text_hash(str(get_value(tool, "description", ""))),
            "input_schema_hash": _canonical_hash(schema),
        }

    def _resource_definition(self, resource: object) -> dict[str, Any]:
        uri = str(
            get_value(
                resource,
                "uri",
                get_value(resource, "uri_template", get_value(resource, "uriTemplate", "")),
            )
        )
        return {
            "uri": uri,
            "name": str(get_value(resource, "name", "")),
            "mime_type": str(get_value(resource, "mime_type", get_value(resource, "mimeType", ""))),
            "description_hash": _text_hash(str(get_value(resource, "description", ""))),
        }

    def _prompt_definition(self, prompt: object) -> dict[str, Any]:
        name = str(get_value(prompt, "name", "unknown"))
        arguments = get_value(prompt, "arguments", ()) or ()
        return {
            "id": self.prompt_contract_id(name),
            "name": name,
            "description_hash": _text_hash(str(get_value(prompt, "description", ""))),
            "arguments_hash": _canonical_hash(object_summary(arguments, self.policy)),
        }

    def _capability_snapshot(self, kind: str, entries: list[dict[str, Any]], cursor: Any) -> None:
        self._append(
            events_pb2.MCP_CAPABILITY_SNAPSHOT,
            {
                "server_id": self.identity.canonical_id,
                "kind": kind,
                "entries": entries,
                "page_hash": _canonical_hash(entries),
                "next_cursor_present": cursor is not None,
            },
        )

    def _content_fingerprint(self, content: object) -> dict[str, Any]:
        content_type = str(get_value(content, "type", type(content).__name__))
        uri = str(get_value(content, "uri", ""))
        mime_type = str(get_value(content, "mime_type", get_value(content, "mimeType", "")))
        raw = _content_bytes(content)
        return {
            "type": content_type,
            "uri": uri,
            "mime_type": mime_type,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def _append_tool_result(
        self,
        event_type: int,
        run_id: str,
        correlation_id: str,
        causation_id: str,
        payload: dict[str, Any],
        begin: int,
        *,
        result: object | None = None,
        error: BaseException | None = None,
        protocol_error: bool = False,
    ) -> None:
        result_payload = {
            **payload,
            "duration_ns": time.perf_counter_ns() - begin,
            "protocol_error": protocol_error,
        }
        if result is not None:
            result_payload["result_hash"] = _canonical_hash(object_summary(result, self.policy))
        if error is not None:
            result_payload.update(
                error_type=type(error).__name__, error=self.policy.sanitize(str(error))
            )
        self.repository.append_event(
            event_type,
            run_id=run_id,
            producer=self.producer,
            payload=result_payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def _append(self, event_type: int, payload: dict[str, Any]) -> None:
        context = current_context()
        run_id = context.run_id if context else self.session_run_id
        self.repository.append_event(
            event_type,
            run_id=run_id,
            producer=self.producer,
            payload=payload,
            correlation_id=context.correlation_id if context else run_id,
            causation_id=context.causation_id if context else "",
        )


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _content_bytes(content: object) -> bytes:
    for name in ("text", "blob", "data"):
        value = get_value(content, name)
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
    return repr(content).encode("utf-8")
