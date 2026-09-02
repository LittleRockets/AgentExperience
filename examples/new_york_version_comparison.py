"""Compare one no-experience baseline with v0.1, v0.2 and v0.3 experience paths."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

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
    ExperienceRetriever,
    HarnessState,
    LifecycleManager,
    Outcome,
    PromotionPolicy,
    Repository,
    RetrievalQuery,
    RuleSelector,
    RunOutcome,
    SelectionDecision,
    TokenBudget,
    Utf8TokenEstimator,
    agent_experience,
)
from agent_experience.events.factory import unpack_payload
from agent_experience.schema import events_pb2, experience_pb2


def _call_result(call: Any, score: Any, content_file: str) -> dict[str, Any]:
    call_values = asdict(call)
    content = str(call_values.pop("content"))
    return {
        "call": call_values | {"content": f"see {content_file}"},
        "rubric": asdict(score),
        "structure": _structure_metrics(content),
    }


def _activate_isolated(runtime: Any, definition: Any) -> Any:
    candidate = experience_pb2.ExperienceDefinition()
    candidate.CopyFrom(definition)
    candidate.experience_id = definition.experience_id + "-version-benchmark"
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
                evaluation_id=f"nyc-version-{index}",
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
    return lifecycle.promote(candidate.experience_id, manual_approval=True)


def _v02_select(runtime: Any, definition: Any) -> tuple[Any, Any]:
    """Execute the frozen v0.2 ACTIVE retrieval and rule-budget algorithm."""

    advice = ExperienceRetriever(runtime.repository).search(
        RetrievalQuery(
            text=PROMPT,
            task_type="travel_plan",
            limit=5,
        )
    )
    selected_advice = next(
        (item for item in advice if item.experience_id == definition.experience_id), None
    )
    if selected_advice is None:
        raise RuntimeError("v0.2 ACTIVE-only retrieval did not select the benchmark experience")
    estimator = Utf8TokenEstimator()
    selection = RuleSelector().select(
        definition,
        TokenBudget(
            max_context_tokens=8192,
            base_input_tokens=estimator.estimate(PROMPT, model_id=MODEL),
            reserved_output_tokens=3000,
            max_experience_tokens=96,
        ),
    )
    if not selection.selected:
        raise RuntimeError("v0.2 rule budget rejected every experience rule")
    return selected_advice, selection


def _with_advice(summary: str, steps: tuple[str, ...]) -> str:
    advice = "\n".join((summary, *steps)).strip()
    return PROMPT + "\n\n【AgentExperience 选择结果】\n" + advice


def _delta(arm: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float | int]:
    arm_call = arm["call"]
    base_call = baseline["call"]
    arm_rubric = arm["rubric"]
    base_rubric = baseline["rubric"]
    arm_structure = arm["structure"]
    base_structure = baseline["structure"]
    return {
        "rubric_score": int(arm_rubric["total"]) - int(base_rubric["total"]),
        "prompt_tokens": int(arm_call["prompt_tokens"]) - int(base_call["prompt_tokens"]),
        "completion_tokens": int(arm_call["completion_tokens"])
        - int(base_call["completion_tokens"]),
        "latency_seconds": round(
            float(arm_call["elapsed_seconds"]) - float(base_call["elapsed_seconds"]), 3
        ),
        "characters": int(arm_structure["characters"]) - int(base_structure["characters"]),
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
        source_definition = max(definitions, key=lambda value: value.generation)

    v01_selection = select_rules(source_definition, PROMPT)
    if not v01_selection.selected:
        raise RuntimeError("v0.1 legacy RuleSelector 没有选出规则")

    runtime = agent_experience(output / "v0.3-repository")
    active_definition = _activate_isolated(runtime, source_definition)
    v02_advice, v02_selection = _v02_select(runtime, active_definition)
    v02_prompt = _with_advice(v02_advice.summary, tuple(v02_selection.rendered.splitlines()))

    run = runtime.start(
        PROMPT,
        task_id="new-york-two-day",
        harness="nyc-version-comparison",
        metadata={"task_type": "travel_plan", "comparison_arm": "v0.3"},
    )
    v03_selection = run.select(
        HarnessState(
            task=PROMPT,
            harness_policy={
                "task_type": "travel_plan",
                "max_experience_risk": "medium",
                "max_experience_composition": 1,
            },
            budget={
                "max_context_tokens": 8192,
                "base_input_tokens": 84,
                "reserved_output_tokens": 3000,
                "max_experience_tokens": 96,
            },
        )
    )[0]
    v03_adopted = v03_selection.decision is SelectionDecision.SELECTED
    v03_prompt = (
        _with_advice(v03_selection.summary, v03_selection.steps) if v03_adopted else PROMPT
    )

    prompts = {
        "baseline_no_experience": PROMPT,
        "v0.1_with_experience": experience_prompt(PROMPT, v01_selection),
        "v0.2_with_experience": v02_prompt,
        "v0.3_with_experience": v03_prompt,
    }
    calls = {
        key: call_deepseek(prompt, label=key, temperature=0.0)
        for key, prompt in prompts.items()
    }
    scores = {
        key: score_plan(call.content, 2, finish_reason=call.finish_reason)
        for key, call in calls.items()
    }
    protocol_outcome = RunOutcome(
        Outcome.SUCCESS if scores["v0.3_with_experience"].passed else Outcome.FAILURE,
        result={"score": scores["v0.3_with_experience"].total},
        tokens=calls["v0.3_with_experience"].total_tokens,
        latency_ms=calls["v0.3_with_experience"].elapsed_seconds * 1000,
    )
    if v03_adopted:
        run.feedback(
            protocol_outcome,
            experience_id=v03_selection.experience_id,
            revision_id=v03_selection.revision_id,
            accepted=True,
        )
    run.complete(protocol_outcome)

    files = {
        "baseline_no_experience": "baseline-no-experience.md",
        "v0.1_with_experience": "v0.1-with-experience.md",
        "v0.2_with_experience": "v0.2-with-experience.md",
        "v0.3_with_experience": "v0.3-with-experience.md",
    }
    arms: dict[str, dict[str, Any]] = {}
    for key, call in calls.items():
        (output / files[key]).write_text(call.content, encoding="utf-8")
        arms[key] = _call_result(call, scores[key], files[key])

    selection_event = next(
        event
        for event in reversed(tuple(runtime.repository.events()))
        if event.event_type == events_pb2.EXPERIENCE_ADVISED
        and event.attributes.get("selection_contract") == "0.3"
    )
    baseline_arm = arms["baseline_no_experience"]
    report = {
        "status": "COMPLETED",
        "session": session,
        "model": MODEL,
        "temperature": 0.0,
        "base_prompt": PROMPT,
        "fairness": {
            "same_system_prompt": True,
            "same_base_user_content": True,
            "baseline_has_experience": False,
            "v0.2_v0.3_effective_prompts_equal": v02_prompt == v03_prompt,
            "warning": (
                "即使 temperature=0，远程模型也未必保证逐字确定；当有效 Prompt 相同，"
                "文本差异不能归因于选择协议版本。"
            ),
        },
        "source_experience": {
            "repository": str(source),
            "experience_id": source_definition.experience_id,
            "revision_id": source_definition.revision_id,
            "status": experience_pb2.ExperienceStatus.Name(source_definition.status),
        },
        "isolated_active_experience": {
            "experience_id": active_definition.experience_id,
            "revision_id": active_definition.revision_id,
            "status": experience_pb2.ExperienceStatus.Name(active_definition.status),
            "activation_scope": "isolated benchmark only",
        },
        "selection": {
            "v0.1": {
                "path": "legacy RuleSelector direct injection",
                "selected_rule_ids": [rule.rule_id for rule in v01_selection.selected],
                "estimated_tokens": v01_selection.estimated_tokens,
            },
            "v0.2": {
                "path": "frozen ACTIVE retrieval + rule token budget",
                "experience_id": v02_advice.experience_id,
                "score": v02_advice.score,
                "selected_rule_ids": [rule.rule_id for rule in v02_selection.selected],
                "estimated_tokens": v02_selection.estimated_tokens,
            },
            "v0.3": {
                "path": "Policy Object hard filters + adaptive score + rule token budget",
                "decision": v03_selection.decision.value,
                "adopted": v03_adopted,
                "experience_id": v03_selection.experience_id,
                "reason_codes": list(v03_selection.reason_codes),
                "audit": unpack_payload(selection_event),
            },
        },
        "arms": arms,
        "delta_vs_baseline": {
            key: _delta(arm, baseline_arm)
            for key, arm in arms.items()
            if key != "baseline_no_experience"
        },
        "audit": {
            "events_verified": runtime.repository.verify(),
            "active_runs_after": runtime.active_run_count,
        },
        "limitations": [
            "单内容、单次生成不能证明统计显著性或版本净收益",
            "规则评分存在100分天花板效应",
            "结构计数不等于旅行事实正确性",
            "v0.2为冻结算法复现；当前安装包的ExperienceRun.select正式执行v0.3",
        ],
    }
    runtime.close()
    (output / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n完整输出：{output.resolve()}")


if __name__ == "__main__":
    main()
