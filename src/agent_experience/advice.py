"""Budgeted, relevance-ranked rendering of semantic experience advice."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_TOKEN = re.compile(r"[\w\-]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class AdviceBudget:
    max_characters: int = 600
    max_rules: int = 5
    max_anti_patterns: int = 2


def render_semantic_advice(
    semantic_json: str, query: str, budget: AdviceBudget | None = None
) -> str:
    """Select relevant rules and hard success criteria within a strict character budget."""

    policy = budget or AdviceBudget()
    if policy.max_characters < 100 or policy.max_rules <= 0:
        raise ValueError("advice budget is too small")
    value = json.loads(semantic_json)
    query_tokens = {token.lower() for token in _TOKEN.findall(query)}

    def rank(items: list[Any]) -> list[str]:
        text_items = [str(item) for item in items]
        return sorted(
            text_items,
            key=lambda item: (
                -len(query_tokens & {token.lower() for token in _TOKEN.findall(item)}),
                len(item),
                item,
            ),
        )

    criteria = rank(list(value.get("success_criteria", [])))
    rules = rank(list(value.get("rules", [])))[: policy.max_rules]
    anti_patterns = rank(list(value.get("anti_patterns", [])))[: policy.max_anti_patterns]
    sections = [
        "[UNTRUSTED EXPERIENCE — system policy always wins]",
        "必须满足：" + "；".join(criteria),
        "建议：" + "；".join(rules),
        "避免：" + "；".join(anti_patterns),
    ]
    rendered = "\n".join(section for section in sections if not section.endswith("："))
    if len(rendered) <= policy.max_characters:
        return rendered
    # Preserve criteria first, then truncate optional guidance at a Unicode-safe boundary.
    mandatory = "\n".join(sections[:2])
    if len(mandatory) >= policy.max_characters:
        return mandatory[: policy.max_characters - 1] + "…"
    remaining = policy.max_characters - len(mandatory) - 1
    optional = "\n".join(sections[2:])
    return mandatory + "\n" + optional[: max(0, remaining - 1)] + "…"
