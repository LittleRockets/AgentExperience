from __future__ import annotations

import unittest

from agent_experience.observer import ToolRegistry, ToolSpec


class ToolRegistryTests(unittest.TestCase):
    def test_register_resolve_and_list(self) -> None:
        registry = ToolRegistry()
        first = ToolSpec("local://z", "z", lambda: None)
        second = ToolSpec("local://a", "a", lambda: None, idempotent=True)
        registry.register(first)
        registry.register(second)

        self.assertIs(registry.get("local://a"), second)
        self.assertEqual([item.contract_id for item in registry.list()], ["local://a", "local://z"])

    def test_duplicate_contract_is_rejected(self) -> None:
        registry = ToolRegistry()
        registry.register(ToolSpec("local://tool", "tool", lambda: None))
        with self.assertRaises(ValueError):
            registry.register(ToolSpec("local://tool", "other", lambda: None))


if __name__ == "__main__":
    unittest.main()
