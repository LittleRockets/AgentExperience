from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent_experience.adapters.mcp import MCPServerIdentity, ObservedClientSession
from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2
from agent_experience.storage import Repository

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class FakeSession:
    def __init__(self) -> None:
        self.raise_tool = False

    async def initialize(self, *args: Any, **kwargs: Any) -> object:
        return SimpleNamespace(
            server_info=SimpleNamespace(name="demo", version="1.2.3"),
            protocol_version="2025-06-18",
            capabilities={"tools": {"listChanged": True}, "resources": {}},
        )

    async def list_tools(self, *args: Any, **kwargs: Any) -> object:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="search",
                    title="Search",
                    description="private description",
                    input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                )
            ],
            next_cursor="page-2",
        )

    async def list_resources(self, *args: Any, **kwargs: Any) -> object:
        return SimpleNamespace(
            resources=[SimpleNamespace(uri="docs://guide", name="guide", mime_type="text/plain")],
            next_cursor=None,
        )

    async def list_resource_templates(self, *args: Any, **kwargs: Any) -> object:
        return SimpleNamespace(resource_templates=[], next_cursor=None)

    async def list_prompts(self, *args: Any, **kwargs: Any) -> object:
        return SimpleNamespace(
            prompts=[SimpleNamespace(name="review", description="review secret", arguments=[])],
            next_cursor=None,
        )

    async def call_tool(self, name: str, arguments: object, *args: Any, **kwargs: Any) -> object:
        if self.raise_tool:
            raise TimeoutError("server timeout")
        return SimpleNamespace(
            is_error=name == "broken",
            content=[SimpleNamespace(type="text", text="sensitive tool result")],
            structured_content={"token": "secret", "answer": 42},
        )

    async def read_resource(self, uri: str, *args: Any, **kwargs: Any) -> object:
        return SimpleNamespace(
            contents=[SimpleNamespace(uri=uri, mime_type="text/plain", text="private body")]
        )

    async def get_prompt(self, name: str, arguments: object, *args: Any, **kwargs: Any) -> object:
        return SimpleNamespace(messages=[SimpleNamespace(role="user", text="private prompt")])


class MCPAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_server_identity_is_stable_and_scoped(self) -> None:
        first = MCPServerIdentity("corp", "server", "1", "stdio:abc")
        second = MCPServerIdentity("corp", "server", "1", "stdio:abc")
        different = MCPServerIdentity("other", "server", "1", "stdio:abc")
        self.assertEqual(first.canonical_id, second.canonical_id)
        self.assertNotEqual(first.canonical_id, different.canonical_id)

    def test_capabilities_calls_resources_and_prompts_are_observed(self) -> None:
        async def scenario(path: Path) -> list[events_pb2.EventEnvelope]:
            session = FakeSession()
            with Repository(path) as repository:
                observed = ObservedClientSession(
                    session,
                    repository,
                    trust_domain="test",
                    transport_identity="in-memory",
                )
                await observed.initialize()
                await observed.list_tools(cursor=None)
                await observed.list_resources()
                await observed.list_resource_templates()
                await observed.list_prompts()
                result = await observed.call_tool("search", {"token": "do-not-store"})
                self.assertEqual(result.structured_content["answer"], 42)
                await observed.read_resource("docs://guide")
                await observed.get_prompt("review", {"topic": "security"})
                return list(repository.events())

        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            events = asyncio.run(scenario(Path(directory) / "repo"))

        types = [event.event_type for event in events]
        self.assertEqual(types.count(events_pb2.MCP_CAPABILITY_SNAPSHOT), 4)
        self.assertIn(events_pb2.TOOL_CALL_COMPLETED, types)
        self.assertIn(events_pb2.MCP_RESOURCE_READ, types)
        self.assertIn(events_pb2.MCP_PROMPT_RENDERED, types)
        serialized_payloads = " ".join(str(unpack_payload(event)) for event in events)
        self.assertNotIn("private body", serialized_payloads)
        self.assertNotIn("private prompt", serialized_payloads)
        self.assertNotIn("sensitive tool result", serialized_payloads)
        self.assertNotIn("do-not-store", serialized_payloads)
        self.assertIn("[REDACTED]", serialized_payloads)

    def test_protocol_error_and_exception_are_tool_failures(self) -> None:
        async def scenario(path: Path) -> list[int]:
            session = FakeSession()
            with Repository(path) as repository:
                observed = ObservedClientSession(session, repository, trust_domain="test")
                await observed.initialize()
                await observed.call_tool("broken", {})
                session.raise_tool = True
                with self.assertRaises(TimeoutError):
                    await observed.call_tool("timeout", {})
                return [event.event_type for event in repository.events()]

        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            types = asyncio.run(scenario(Path(directory) / "repo"))
        self.assertEqual(types.count(events_pb2.TOOL_CALL_STARTED), 2)
        self.assertEqual(types.count(events_pb2.TOOL_CALL_FAILED), 2)

    def test_real_mcp_type_aliases_when_sdk_is_installed(self) -> None:
        try:
            from mcp import types
        except ImportError:
            self.skipTest("MCP optional dependency is not installed")

        async def scenario(path: Path) -> tuple[dict[str, object], list[int]]:
            class TypedSession(FakeSession):
                async def call_tool(
                    self, name: str, arguments: object, *args: Any, **kwargs: Any
                ) -> object:
                    return types.CallToolResult(content=[], isError=True)

            with Repository(path) as repository:
                observed = ObservedClientSession(TypedSession(), repository, trust_domain="test")
                observed.identity = MCPServerIdentity("test", "typed")
                template = types.ResourceTemplate(
                    name="docs", uriTemplate="docs://{name}", mimeType="text/plain"
                )
                definition = observed._resource_definition(template)
                await observed.call_tool("broken", {})
                event_types = [event.event_type for event in repository.events()]
                return definition, event_types

        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            definition, event_types = asyncio.run(scenario(Path(directory) / "repo"))
        self.assertEqual(definition["uri"], "docs://{name}")
        self.assertIn(events_pb2.TOOL_CALL_FAILED, event_types)


if __name__ == "__main__":
    unittest.main()
