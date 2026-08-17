"""Run a real DeepSeek A/B test for the existing New York two-day travel example."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from deepseek_experience_demo import (
    MODEL,
    call_deepseek,
    experience_prompt,
    score_plan,
    select_rules,
)

from agent_experience import ExperienceCatalog, Repository
from agent_experience.schema import experience_pb2

PROMPT = (
    "为第一次去纽约的旅行者制定2日计划。输出中文，必须逐日安排，并兼顾经典景点、"
    "每日交通与节奏、住宿区域、餐饮和人民币预算。动态价格、班次、开放时间、签证信息"
    "必须提示按实际日期复核。"
)


def _latest_repository() -> Path:
    configured = os.environ.get("AGENT_EXPERIENCE_SOURCE_REPOSITORY")
    if configured:
        return Path(configured)
    candidates = sorted(path for path in Path("demo-repository").iterdir() if path.is_dir())
    if not candidates:
        raise RuntimeError("未找到 demo-repository；请先运行 deepseek_experience_demo.py")
    return candidates[-1]


def _structure_metrics(content: str) -> dict[str, int]:
    return {
        "characters": len(content),
        "markdown_tables": content.count("|---"),
        "time_slots": content.count(":00") + content.count(":30"),
        "currency_mentions": content.count("元") + content.count("人民币"),
        "verification_mentions": sum(
            content.count(value) for value in ("复核", "官网", "官方", "实际日期")
        ),
    }


def main() -> None:
    session = os.environ.get("AGENT_EXPERIENCE_NYC_SESSION", time.strftime("%Y%m%d-%H%M%S"))
    output = Path("demo-output") / f"nyc-{session}"
    output.mkdir(parents=True, exist_ok=False)
    source = _latest_repository()
    with Repository(source) as repository:
        definitions = tuple(ExperienceCatalog(repository).definitions().values())
        if not definitions:
            raise RuntimeError(f"{source} 中没有可用旅行经验")
        definition = max(definitions, key=lambda value: value.generation)
        selection = select_rules(definition, PROMPT)
    if not selection.selected:
        raise RuntimeError("旅行经验未通过 Token 预算选择，无法执行 A/B")

    baseline = call_deepseek(PROMPT, label="纽约2日：Baseline（不注入经验）")
    experienced = call_deepseek(
        experience_prompt(PROMPT, selection), label="纽约2日：AgentExperience"
    )
    baseline_score = score_plan(baseline.content, 2, finish_reason=baseline.finish_reason)
    experienced_score = score_plan(
        experienced.content, 2, finish_reason=experienced.finish_reason
    )
    report = {
        "status": "COMPLETED",
        "session": session,
        "model": MODEL,
        "source_repository": str(source),
        "prompt": PROMPT,
        "experience": {
            "experience_id": definition.experience_id,
            "revision_id": definition.revision_id,
            "source_status": experience_pb2.ExperienceStatus.Name(definition.status),
            "selection_path": "legacy example RuleSelector (not ExperienceRun.select)",
            "selected_rule_ids": [rule.rule_id for rule in selection.selected],
            "estimated_injection_tokens": selection.estimated_tokens,
            "rendered_injection": selection.rendered,
        },
        "baseline": {
            "call": asdict(baseline) | {"content": "see baseline.md"},
            "rubric": asdict(baseline_score),
            "structure": _structure_metrics(baseline.content),
        },
        "agentexperience": {
            "call": asdict(experienced) | {"content": "see with-agentexperience.md"},
            "rubric": asdict(experienced_score),
            "structure": _structure_metrics(experienced.content),
        },
        "delta": {
            "rubric_score": experienced_score.total - baseline_score.total,
            "prompt_tokens": experienced.prompt_tokens - baseline.prompt_tokens,
            "completion_tokens": experienced.completion_tokens - baseline.completion_tokens,
            "latency_seconds": round(
                experienced.elapsed_seconds - baseline.elapsed_seconds, 3
            ),
            "characters": len(experienced.content) - len(baseline.content),
        },
        "limitations": [
            "单次非配对确定性生成不能证明统计显著性",
            "规则评分器可能出现100分天花板效应",
            "结构计数只描述输出差异，不等同于旅行事实正确性",
            "源经验为QUARANTINED；旧示例RuleSelector路径不代表v0.2 ACTIVE-only协议采用",
        ],
    }
    (output / "baseline.md").write_text(baseline.content, encoding="utf-8")
    (output / "with-agentexperience.md").write_text(experienced.content, encoding="utf-8")
    (output / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n完整输出：{output.resolve()}")


if __name__ == "__main__":
    main()
