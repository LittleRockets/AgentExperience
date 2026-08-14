"""Conservative conversion of runtime values into event-safe summaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    }
)


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """Bound and redact arbitrary values before they enter an observation event."""

    sensitive_keys: frozenset[str] = field(default_factory=lambda: _DEFAULT_SENSITIVE_KEYS)
    max_string_length: int = 512
    max_collection_items: int = 32
    max_depth: int = 4
    replacement: str = "[REDACTED]"

    def sanitize(self, value: Any, *, _depth: int = 0) -> Any:
        """Return a JSON-compatible, size-bounded representation of ``value``."""

        if _depth >= self.max_depth:
            return "[MAX_DEPTH]"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._truncate(value)
        if isinstance(value, bytes):
            return f"[BYTES:{len(value)}]"
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= self.max_collection_items:
                    sanitized["[TRUNCATED]"] = len(value) - self.max_collection_items
                    break
                text_key = str(key)
                sanitized[text_key] = (
                    self.replacement
                    if text_key.casefold() in self.sensitive_keys
                    else self.sanitize(item, _depth=_depth + 1)
                )
            return sanitized
        if isinstance(value, Sequence):
            items = value[: self.max_collection_items]
            result = [self.sanitize(item, _depth=_depth + 1) for item in items]
            if len(value) > self.max_collection_items:
                result.append(f"[TRUNCATED:{len(value) - self.max_collection_items}]")
            return result
        return self._truncate(repr(value))

    def _truncate(self, value: str) -> str:
        if len(value) <= self.max_string_length:
            return value
        return f"{value[: self.max_string_length]}…"
