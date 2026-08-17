"""Compare Baseline, legacy v0.1 experience, and the current v0.2 protocol."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from deepseek_experience_demo import (
    MODEL,
    call_deepseek,
    experience_prompt,
    score_plan,
    select_rules,
)
from new_york_baseline_agentexperience import PROMPT, _latest_repository, _structure_metrics

from agent_experience import (
    ExperienceCatalog,
    HarnessState,
    LifecycleManager,
    Outcome,
    PromotionPolicy,
    Repository,
    RunOutcome,
    SelectionDecision,
    agent_experience,
)
from agent_experience.schema import events_pb2, experience_pb2


def _call_result(call: object, score: object, content_file: str) -> dict[str, object]:
    call_values = asdict(call)  # type: ignore[arg-type]
    content = str(call_values.pop("content"))
    return {
        "call": call_values | {"content": f"see {content_file}"},
        "rubric": asdict(score),  # type: ignore[arg-type]
        "structure": _structure_metrics(content),
    }


def main() -> None:
    session = os.environ.get("AGENT_EXPERIENCE_VERSION_SESSION", time.strftime("%Y%m%d-%H%M%S"))
    output = Path("demo-output") / f"nyc-version-comparison-{session}"
    output.mkdir(parents=True, exist_ok=False)
    source = _latest_repository()
    with Repository(source) as source_repository:
        definitions = tuple(ExperienceCatalog(source_repository).definitions().values())
        if not definitions:
            raise RuntimeError(f"{source} 中没有旅行经验")
        definition = max(definitions, key=lambda value: value.generation)

    legacy_selection = select_rules(definition, PROMPT)
    if not legacy_selection.selected:
        raise RuntimeError("v0.1 legacy RuleSelector 没有选出规则")

    runtime = agent_experience(output / "v0.2-repository")
    candidate = experience_pb2.ExperienceDefinition()
    candidate.CopyFrom(definition)
    candidate.experience_id = definition.experience_id + "-v02-benchmark"
    candidate.revision_id = str(uuid.uuid4())
    candidate.generation = 1
    candidate.status = experience_pb2.CANDIDATE
    runtime.repository.append_event(
        events_pb2.EXPERIENCE_CANDIDATE_CREATED,
        run_id="",
        producer="nyc-version-comparison/isolated-benchmark-candidate",
        payload=candidate,
        attributes={
            "source_status": experience_pb2.ExperienceStatus.Name(definition.status),
            "activation_scope": "isolated_benchmark_only",
        },
    )
    lifecycle = LifecycleManager(runtime.repository, PromotionPolicy(2, 3, 2, True))
    for index, source_run_id in enumerate(candidate.source_run_ids[:3]):
        lifecycle.record_evaluation(
            experience_pb2.EvaluationEvent(
                evaluation_id=f"nyc-v02-{index}",
                experience_id=candidate.experience_id,
                revision_id=candidate.revision_id,
                run_id=source_run_id,
                outcome=experience_pb2.EvaluationEvent.SUCCESS,
                confidence=1.0,
                evaluator_id="demo-rubric/v1",
                evaluator_version="1",
                evidence_references=[f"source-run:{source_run_id}"],
            )
        )
    lifecycle.promote(candidate.experience_id)
    active_definition = lifecycle.promote(candidate.experience_id, manual_approval=True)
    run = runtime.start(
        PROMPT,
        task_id="new-york-two-day",
        harness="nyc-version-comparison",
        metadata={"task_type": "travel_plan"},
    )
    v02_selection = run.select(
        HarnessState(
            task=PROMPT,
            harness_policy={"task_type": "travel_plan"},
            budget={
                "max_context_tokens": 8192,
                "base_input_tokens": 84,
                "reserved_output_tokens": 3000,
                "max_experience_tokens": 96,
            },
        )
    )[0]
    v02_adopted = v02_selection.decision is SelectionDecision.SELECTED
    v02_prompt = PROMPT
    if v02_adopted:
        advice = "\n".join((v02_selection.summary, *v02_selection.steps)).strip()
        v02_prompt += "\n\n【AgentExperience 选择结果】\n" + advice

    baseline = call_deepseek(PROMPT, label="纽约2日：Baseline")
    legacy = call_deepseek(
        experience_prompt(PROMPT, legacy_selection), label="纽约2日：v0.1 with experience"
    )
    protocol = call_deepseek(v02_prompt, label="纽约2日：v0.2 protocol")
    baseline_score = score_plan(baseline.content, 2, finish_reason=baseline.finish_reason)
    legacy_score = score_plan(legacy.content, 2, finish_reason=legacy.finish_reason)
    protocol_score = score_plan(protocol.content, 2, finish_reason=protocol.finish_reason)
    protocol_outcome = RunOutcome(
        Outcome.SUCCESS if protocol_score.passed else Outcome.FAILURE,
        result={"score": protocol_score.total},
        tokens=protocol.total_tokens,
        latency_ms=protocol.elapsed_seconds * 1000,
    )
    if v02_adopted:
        run.feedback(
            protocol_outcome,
            experience_id=v02_selection.experience_id,
            revision_id=v02_selection.revision_id,
            accepted=True,
        )
    run.complete(protocol_outcome)

    files = {
        "baseline": "baseline.md",
        "v0.1_with_experience": "v0.1-with-experience.md",
        "v0.2_protocol": "v0.2-protocol.md",
    }
    (output / files["baseline"]).write_text(baseline.content, encoding="utf-8")
    (output / files["v0.1_with_experience"]).write_text(legacy.content, encoding="utf-8")
    (output / files["v0.2_protocol"]).write_text(protocol.content, encoding="utf-8")
    report = {
        "status": "COMPLETED",
        "session": session,
        "model": MODEL,
        "prompt": PROMPT,
        "source_experience": {
            "repository": str(source),
            "experience_id": definition.experience_id,
            "revision_id": definition.revision_id,
            "status": experience_pb2.ExperienceStatus.Name(definition.status),
        },
        "v0.2_benchmark_experience": {
            "experience_id": active_definition.experience_id,
            "revision_id": active_definition.revision_id,
            "status": experience_pb2.ExperienceStatus.Name(active_definition.status),
            "activation_scope": "isolated benchmark only",
            "evidence_runs": list(candidate.source_run_ids[:3]),
        },
        "v0.1_selection": {
            "path": "legacy RuleSelector direct delta-rule injection",
            "adopted": True,
            "selected_rule_ids": [rule.rule_id for rule in legacy_selection.selected],
            "estimated_tokens": legacy_selection.estimated_tokens,
            "rendered": legacy_selection.rendered,
        },
        "v0.2_selection": {
            "path": "ExperienceRun.select (ACTIVE-only protocol)",
            "decision": v02_selection.decision.value,
            "adopted": v02_adopted,
            "reason_codes": list(v02_selection.reason_codes),
            "summary": v02_selection.summary,
            "experience_id": v02_selection.experience_id,
        },
        "arms": {
            "baseline": _call_result(baseline, baseline_score, files["baseline"]),
            "v0.1_with_experience": _call_result(
                legacy, legacy_score, files["v0.1_with_experience"]
            ),
            "v0.2_protocol": _call_result(protocol, protocol_score, files["v0.2_protocol"]),
        },
        "v0.2_audit": {
            "events_verified": runtime.repository.verify(),
            "active_runs_after": runtime.active_run_count,
        },
        "interpretation": (
            "v0.2 is only 'with experience' when decision=selected and adopted=true; "
            "an abstained result is intentionally reported as protocol safety behavior."
        ),
    }
    runtime.close()
    (output / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n完整输出：{output.resolve()}")


if __name__ == "__main__":
    main()
