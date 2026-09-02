"""Transparent end-to-end DeepSeek demo for AgentExperience's generic APIs.

Travel is only the demo domain. Domain facts are converted here—not in the library—
to generic RunFeatures and BenefitMeasurement records.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_experience import (
    BenefitLedger,
    BreakEvenPolicy,
    DeterministicMiner,
    LifecycleManager,
    PromotionPolicy,
    Repository,
    RuleSelector,
    RunFeatures,
    TokenBudget,
    Utf8TokenEstimator,
    build_baseline_profile,
    definition_from_delta,
    measure_benefit,
)
from agent_experience.schema import events_pb2, experience_pb2

try:
    from deepseek_demo_local import DEEPSEEK_API_KEY as LOCAL_DEEPSEEK_API_KEY
except ImportError:
    LOCAL_DEEPSEEK_API_KEY = ""

MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
SESSION = os.environ.get("AGENT_EXPERIENCE_DEMO_SESSION", time.strftime("%Y%m%d-%H%M%S"))
REPOSITORY_PATH = Path("demo-repository") / SESSION
OUTPUT_PATH = Path("demo-output") / SESSION
SYSTEM = "你是严谨的旅行规划助手。只根据用户要求工作，不虚构实时价格、班次或开放状态。"
BASE_TASK = (
    "为第一次去{country}的旅行者制定{days}日计划。输出中文，必须逐日安排，并兼顾经典景点、"
    "自然体验、城市间交通、每日节奏、住宿区域、餐饮和人民币预算。动态价格、班次、开放时间、"
    "签证信息必须提示按实际日期复核。"
)


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


_configure_console()


@dataclass(frozen=True, slots=True)
class ModelCall:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    elapsed_seconds: float
    model: str
    finish_reason: str


@dataclass(frozen=True, slots=True)
class PlanScore:
    requested_days: int
    detected_days: int
    day_completeness: int
    transport: int
    accommodation: int
    budget: int
    food: int
    dynamic_warning: int
    route_coherence: int
    excessive_claim_penalty: int
    truncation_penalty: int
    total: int
    passed: bool
    evidence: tuple[str, ...]


def call_deepseek(
    prompt: str, *, label: str, temperature: float = 0.2, max_attempts: int = 3
) -> ModelCall:
    api_key = os.environ.get("DEEPSEEK_API_KEY") or LOCAL_DEEPSEEK_API_KEY
    if not api_key:
        raise RuntimeError("请在已忽略的 examples/deepseek_demo_local.py 中配置 API Key")
    uses_experience = "【AgentExperience 选择结果】" in prompt
    print(f"\n{'=' * 88}\nLLM CALL: {label}")
    print(f"model={MODEL} uses_experience={uses_experience}")
    print("--- SYSTEM PROMPT ---\n" + SYSTEM)
    print("--- USER PROMPT ---\n" + prompt)
    body: dict[str, Any] = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "thinking": {"type": "disabled"},
        "max_tokens": 3000,
        "temperature": temperature,
    }
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    started = time.perf_counter()
    payload: dict[str, Any] | None = None
    retryable = (
        http.client.IncompleteRead,
        urllib.error.URLError,
        TimeoutError,
        ConnectionError,
        json.JSONDecodeError,
    )
    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            f"{BASE_URL}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                loaded = json.load(response)
            if not isinstance(loaded, dict):
                raise RuntimeError("DeepSeek response must be a JSON object")
            payload = loaded
            break
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek HTTP {error.code}: {detail}") from error
        except retryable as error:
            if attempt == max_attempts:
                raise RuntimeError(
                    f"DeepSeek transport failed after {max_attempts} attempts: {error}"
                ) from error
            delay = 2**attempt
            print(
                f"DeepSeek transport retry {attempt}/{max_attempts - 1} "
                f"after {type(error).__name__}; waiting {delay}s"
            )
            time.sleep(delay)
    if payload is None:
        raise RuntimeError("DeepSeek transport completed without a response")
    usage = payload.get("usage", {})
    result = ModelCall(
        str(payload["choices"][0]["message"]["content"]),
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
        int(usage.get("total_tokens", 0)),
        round(time.perf_counter() - started, 3),
        str(payload.get("model", MODEL)),
        str(payload["choices"][0].get("finish_reason", "unknown")),
    )
    print("--- LLM RESULT METRICS ---")
    print(
        json.dumps(
            asdict(result) | {"content": f"<{len(result.content)} chars>"},
            ensure_ascii=False,
            indent=2,
        )
    )
    return result


def score_plan(text: str, days: int, *, finish_reason: str = "stop") -> PlanScore:
    detected = len(set(re.findall(r"第\s*(\d+)\s*天", text)))
    day_score = round(25 * min(detected, days) / days)
    checks = {
        "transport": ("交通" in text or "火车" in text or "列车" in text, 15),
        "accommodation": ("住宿" in text or "酒店" in text, 10),
        "budget": ("预算" in text and ("元" in text or "人民币" in text), 15),
        "food": ("餐饮" in text or "午餐" in text or "晚餐" in text, 10),
        "dynamic_warning": (any(word in text for word in ("复核", "核实", "官网", "实际日期")), 10),
        "route_coherence": (detected >= days and len(text) >= days * 300, 15),
    }
    values = {name: points if passed else 0 for name, (passed, points) in checks.items()}
    risky = sum(text.count(phrase) for phrase in ("保证", "一定开放", "价格固定", "无需核实"))
    penalty = min(20, risky * 5)
    truncation = 30 if finish_reason == "length" else 0
    total = max(0, day_score + sum(values.values()) - penalty - truncation)
    evidence = [f"检测到 {detected}/{days} 个逐日标题"] + [
        f"{name}: {'通过' if passed else '缺失'}" for name, (passed, _) in checks.items()
    ]
    return PlanScore(
        requested_days=days,
        detected_days=detected,
        day_completeness=day_score,
        **values,
        excessive_claim_penalty=penalty,
        truncation_penalty=truncation,
        total=total,
        passed=total >= 75 and finish_reason != "length",
        evidence=tuple(evidence),
    )


def score_features(run_id: str, score: PlanScore, call: ModelCall) -> RunFeatures:
    """Demo-domain adapter: deterministic score facts -> generic core features."""
    fields = {
        "day_completeness": score.day_completeness == 25,
        "transport": score.transport > 0,
        "accommodation": score.accommodation > 0,
        "budget": score.budget > 0,
        "food": score.food > 0,
        "dynamic_warning": score.dynamic_warning > 0,
        "route_coherence": score.route_coherence > 0,
    }
    return RunFeatures(
        run_id,
        frozenset(name for name, passed in fields.items() if passed),
        frozenset(name for name, passed in fields.items() if not passed),
        input_tokens=call.prompt_tokens,
        output_tokens=call.completion_tokens,
        latency_ms=round(call.elapsed_seconds * 1000),
    )


def record_seed(repository: Repository, country: str, call: ModelCall, score: PlanScore) -> str:
    run_id = str(uuid.uuid4())
    repository.append_event(
        events_pb2.RUN_STARTED,
        run_id=run_id,
        producer="deepseek-demo/v2",
        payload={"task_type": "travel_plan", "subject": country},
    )
    repository.append_event(
        events_pb2.RUN_COMPLETED,
        run_id=run_id,
        producer="deepseek-demo/v2",
        payload={"duration_ns": round(call.elapsed_seconds * 1_000_000_000)},
    )
    repository.append_event(
        events_pb2.OUTCOME_EVALUATED,
        run_id=run_id,
        producer="demo-rubric/v1",
        payload={
            "outcome": "success" if score.passed else "failure",
            "score": score.total,
            "evidence": list(score.evidence),
        },
    )
    return run_id


def create_validated_experience(
    repository: Repository, features: tuple[RunFeatures, ...]
) -> tuple[experience_pb2.ExperienceDefinition, Any]:
    baseline = build_baseline_profile(
        "deepseek-travel-demo",
        "2",
        system_prompt=SYSTEM,
        output_contract="daily plan, transport, accommodation, food, budget, verification",
        model_id=MODEL,
    )
    mining = DeterministicMiner().mine(baseline, features)
    definition = definition_from_delta(mining, task_type="travel_plan")
    definition.created_by = "deepseek-demo/deterministic-feature-adapter-v2"
    definition.applicability.trigger_keywords.extend(("旅行", "计划"))
    repository.append_event(
        events_pb2.EXPERIENCE_CANDIDATE_CREATED,
        run_id=features[0].run_id,
        producer="deepseek-demo/miner-v2",
        payload=definition,
    )
    manager = LifecycleManager(repository, PromotionPolicy(2, 99, 1, True))
    for feature in features:
        manager.record_evaluation(
            experience_pb2.EvaluationEvent(
                evaluation_id=str(uuid.uuid4()),
                experience_id=definition.experience_id,
                revision_id=definition.revision_id,
                run_id=feature.run_id,
                outcome=experience_pb2.EvaluationEvent.SUCCESS,
                confidence=1,
                evaluator_id="demo-rubric/v1",
                evaluator_version="1",
                evidence_references=[f"run:{feature.run_id}"],
            )
        )
    validated = manager.promote(definition.experience_id)
    return validated, mining


def select_rules(definition: experience_pb2.ExperienceDefinition, base_prompt: str) -> Any:
    estimator = Utf8TokenEstimator()
    budget = TokenBudget(8192, estimator.estimate(SYSTEM + base_prompt, model_id=MODEL), 3000, 96)
    return RuleSelector().select(definition, budget)


def experience_prompt(base_prompt: str, selection: Any) -> str:
    if not selection.selected:
        return base_prompt
    return base_prompt + "\n\n【AgentExperience 选择结果】\n" + selection.rendered


def benefit_for_pair(
    definition: experience_pb2.ExperienceDefinition,
    label: str,
    baseline: ModelCall,
    experienced: ModelCall,
    baseline_score: PlanScore,
    experienced_score: PlanScore,
    *,
    mining_tokens: int,
    mining_latency_ms: int,
) -> experience_pb2.BenefitMeasurement:
    return measure_benefit(
        experience_id=definition.experience_id,
        revision_id=definition.revision_id,
        baseline_id=definition.delta.baseline.baseline_id,
        run_id=label,
        quality_delta=experienced_score.total - baseline_score.total,
        success_rate_delta=float(experienced_score.passed) - float(baseline_score.passed),
        input_token_delta=experienced.prompt_tokens - baseline.prompt_tokens,
        output_token_delta=experienced.completion_tokens - baseline.completion_tokens,
        latency_ms_delta=round((experienced.elapsed_seconds - baseline.elapsed_seconds) * 1000),
        mining_tokens=mining_tokens,
        mining_latency_ms=mining_latency_ms,
        expected_reuse_count=100,
        output_truncated=experienced.finish_reason == "length",
    )


def table_markdown(
    calls: dict[str, ModelCall],
    scores: dict[str, PlanScore],
    definition: experience_pb2.ExperienceDefinition,
    mining: Any,
    selection: Any,
    decisions: dict[str, Any],
    event_count: int,
) -> str:
    keys = (
        "seed_norway",
        "seed_sweden",
        "seed_denmark",
        "austria_base",
        "austria_exp",
        "germany_base",
        "germany_exp",
    )
    columns = (
        "挪威证据",
        "瑞典证据",
        "丹麦证据",
        "奥地利基线",
        "奥地利经验",
        "德国基线",
        "德国经验",
    )
    rows: list[tuple[str, str, list[Any]]] = []

    def add(category: str, metric: str, values: list[Any]) -> None:
        rows.append((category, metric, values))

    add("调用", "调用 LLM", ["是"] * 7)
    add("调用", "使用经验", ["否", "否", "否", "否", "是", "否", "是"])
    add("模型", "输入 Token", [calls[key].prompt_tokens for key in keys])
    add("模型", "输出 Token", [calls[key].completion_tokens for key in keys])
    add("模型", "总 Token", [calls[key].total_tokens for key in keys])
    add("性能", "耗时秒", [calls[key].elapsed_seconds for key in keys])
    add("输出", "字符数", [len(calls[key].content) for key in keys])
    add("输出", "finish_reason", [calls[key].finish_reason for key in keys])
    for label, field in (
        ("总分", "total"),
        ("识别天数", "detected_days"),
        ("交通", "transport"),
        ("住宿", "accommodation"),
        ("预算", "budget"),
        ("餐饮", "food"),
        ("动态复核", "dynamic_warning"),
        ("路线完整", "route_coherence"),
    ):
        add("评分", label, [getattr(scores[key], field) for key in keys])
    add("评分", "通过", [scores[key].passed for key in keys])
    add("经验", "确定性提炼调用 LLM", ["-", "-", "否", "-", "-", "-", "-"])
    add(
        "经验",
        "提炼输入/输出 Token",
        [
            "-",
            "-",
            f"{mining.mining_input_tokens}/{mining.mining_output_tokens}",
            "-",
            "-",
            "-",
            "-",
        ],
    )
    add("经验", "候选规则数", ["-", "-", len(definition.delta.rules), "-", "-", "-", "-"])
    add("经验", "注入规则数", [0, 0, 0, 0, len(selection.selected), 0, len(selection.selected)])
    add(
        "经验",
        "注入估算 Token",
        [0, 0, 0, 0, selection.estimated_tokens, 0, selection.estimated_tokens],
    )
    add(
        "收益",
        "质量差值",
        [
            "-",
            "-",
            "-",
            0,
            decisions["austria"].aggregate.quality_delta,
            0,
            decisions["germany"].aggregate.quality_delta,
        ],
    )
    add(
        "收益",
        "策略通过",
        ["-", "-", "-", "-", decisions["austria"].accepted, "-", decisions["germany"].accepted],
    )
    add(
        "收益",
        "判定原因",
        [
            "-",
            "-",
            "-",
            "-",
            ",".join(decisions["austria"].reasons) or "accepted",
            "-",
            ",".join(decisions["germany"].reasons) or "accepted",
        ],
    )
    add(
        "生命周期",
        "最终状态",
        [
            "证据",
            "证据",
            "证据",
            "-",
            experience_pb2.ExperienceStatus.Name(definition.status),
            "-",
            experience_pb2.ExperienceStatus.Name(definition.status),
        ],
    )
    add("审计", "事件总数", ["-", "-", "-", "-", "-", "-", event_count])
    lines = [
        "# AgentExperience 全流程统一对比表",
        "",
        "| 分类 | 全部对比项目 | " + " | ".join(columns) + " |",
        "|---|---|" + "---:|" * 7,
    ]
    lines.extend(
        "| " + " | ".join([category, metric, *(str(value) for value in values)]) + " |"
        for category, metric, values in rows
    )
    lines.extend(
        [
            "",
            "## 实际选择并注入的规则",
            "",
            "```text",
            selection.rendered or "<无规则：预算或适用性拒绝>",
            "```",
            "",
            "说明：旅行评分器和字段映射仅属于此示例；核心包只处理通用 "
            "feature path、Token 预算与收益测量。",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_PATH.mkdir(parents=True, exist_ok=False)
    print(f"SESSION={SESSION}\nrepository={REPOSITORY_PATH}\noutput={OUTPUT_PATH}")
    print("固定调用 LLM 7 次：3 个独立证据样本 + 奥地利 A/B + 德国泛化 A/B；经验提炼不调用 LLM。")
    calls: dict[str, ModelCall] = {}
    scores: dict[str, PlanScore] = {}
    features: list[RunFeatures] = []
    with Repository(REPOSITORY_PATH) as repository:
        for key, country, days in (
            ("seed_norway", "挪威", 7),
            ("seed_sweden", "瑞典", 6),
            ("seed_denmark", "丹麦", 5),
        ):
            call = call_deepseek(
                BASE_TASK.format(country=country, days=days), label=f"证据样本：{country}{days}日"
            )
            score = score_plan(call.content, days, finish_reason=call.finish_reason)
            calls[key], scores[key] = call, score
            _write(f"{key}.md", call.content)
            run_id = record_seed(repository, country, call, score)
            if score.passed:
                features.append(score_features(run_id, score, call))
            print(
                "--- DETERMINISTIC SCORE ---\n"
                + json.dumps(asdict(score), ensure_ascii=False, indent=2)
            )
        if len(features) < 2:
            raise RuntimeError("少于两个独立成功样本，无法生成通用经验；原始输出已保留")
        validated, mining = create_validated_experience(repository, tuple(features))
        mining_tokens = mining.mining_input_tokens + mining.mining_output_tokens
        print(
            f"MINING: used_llm={mining.used_llm} "
            f"tokens={mining_tokens} rules={len(validated.delta.rules)}"
        )

        selections: dict[str, Any] = {}
        for prefix, country in (("austria", "奥地利"), ("germany", "德国")):
            base_prompt = BASE_TASK.format(country=country, days=5)
            selection = select_rules(validated, base_prompt)
            selections[prefix] = selection
            selected_ids = [rule.rule_id for rule in selection.selected]
            rejected_ids = list(selection.rejected_rule_ids)
            print(
                f"\nRULE SELECTION {country}: selected={selected_ids} "
                f"rejected={rejected_ids} estimated_tokens={selection.estimated_tokens}"
            )
            base = call_deepseek(base_prompt, label=f"{country}五日：无经验基线")
            exp = call_deepseek(
                experience_prompt(base_prompt, selection), label=f"{country}五日：经验组"
            )
            calls[f"{prefix}_base"], calls[f"{prefix}_exp"] = base, exp
            scores[f"{prefix}_base"] = score_plan(base.content, 5, finish_reason=base.finish_reason)
            scores[f"{prefix}_exp"] = score_plan(exp.content, 5, finish_reason=exp.finish_reason)
            _write(f"{prefix}-baseline.md", base.content)
            _write(f"{prefix}-with-experience.md", exp.content)

        ledger = BenefitLedger(repository)
        austria_measurement = benefit_for_pair(
            validated,
            "holdout-austria",
            calls["austria_base"],
            calls["austria_exp"],
            scores["austria_base"],
            scores["austria_exp"],
            mining_tokens=mining.mining_input_tokens + mining.mining_output_tokens,
            mining_latency_ms=mining.mining_latency_ms,
        )
        germany_measurement = benefit_for_pair(
            validated,
            "generalization-germany",
            calls["germany_base"],
            calls["germany_exp"],
            scores["germany_base"],
            scores["germany_exp"],
            mining_tokens=0,
            mining_latency_ms=0,
        )
        policy = BreakEvenPolicy(
            minimum_measurements=1,
            minimum_holdout_samples=1,
            policy_id="demo-predeclared-break-even",
            policy_version="1",
        )
        ledger.record(austria_measurement)
        austria_decision = policy.evaluate(
            ledger.aggregate(validated.experience_id, revision_id=validated.revision_id)
        )
        ledger.record(germany_measurement)
        combined_decision = policy.evaluate(
            ledger.aggregate(validated.experience_id, revision_id=validated.revision_id)
        )
        manager = LifecycleManager(repository, PromotionPolicy(2, 99, 1, True))
        final_definition = validated
        if combined_decision.accepted:
            final_definition = manager.promote_with_benefit(
                validated.experience_id, policy, manual_approval=True
            )
        else:
            final_definition = manager.transition(validated, experience_pb2.QUARANTINED)
        decisions = {"austria": austria_decision, "germany": combined_decision}
        event_count = repository.verify()
        table = table_markdown(
            calls, scores, final_definition, mining, selections["germany"], decisions, event_count
        )
        _write("full-comparison.md", table)
        report = {
            "status": "COMPLETED",
            "session": SESSION,
            "model": MODEL,
            "llm_call_count": 7,
            "mining": {
                "used_llm": mining.used_llm,
                "input_tokens": mining.mining_input_tokens,
                "output_tokens": mining.mining_output_tokens,
                "latency_ms": mining.mining_latency_ms,
            },
            "experience": {
                "id": final_definition.experience_id,
                "revision": final_definition.revision_id,
                "status": experience_pb2.ExperienceStatus.Name(final_definition.status),
                "candidate_rules": len(validated.delta.rules),
                "selected_rules": [rule.rule_id for rule in selections["germany"].selected],
                "rendered_injection": selections["germany"].rendered,
            },
            "decisions": {
                name: {
                    "accepted": decision.accepted,
                    "reasons": list(decision.reasons),
                    "policy_id": decision.policy_id,
                    "policy_version": decision.policy_version,
                    "aggregate": asdict(decision.aggregate),
                }
                for name, decision in decisions.items()
            },
            "calls": {
                key: asdict(call) | {"content": f"see {key}.md"} for key, call in calls.items()
            },
            "scores": {key: asdict(score) for key, score in scores.items()},
            "event_count": event_count,
        }
        _write("report.json", json.dumps(report, ensure_ascii=False, indent=2))
        print("\n--- 全流程统一对比表 ---\n" + table)
        print(f"\n完整结果目录：{OUTPUT_PATH}")


def _write(name: str, content: str) -> None:
    (OUTPUT_PATH / name).write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
