"""Mount a portable package with one path and one line of integration."""

from __future__ import annotations

import sys

from agent_experience import agent_experience

experience = agent_experience("./experience-data")


@experience.tool(capability="document/summarize@1")
def summarize(document: str) -> str:
    """Existing application capability; AgentExperience does not replace its implementation."""

    return document[:200]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python examples/portable_experience_mount.py PACKAGE.exp")
    report = experience.mount(sys.argv[1])
    print(report)
    for binding in report.bindings:
        print(f"{binding.required} -> {binding.local or binding.reason.value}")
    experience.close()


if __name__ == "__main__":
    main()
