from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_experience import (
    BenefitAggregate,
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


class DeltaBenefitTests(unittest.TestCase):
    def test_baseline_profile_accepts_text_and_bytes_for_all_content_fields(self) -> None:
        text_profile = build_baseline_profile(
            "baseline",
            "1",
            system_prompt="系统提示",
            workflow="节点甲 -> 节点乙",
            tool_contract_ids=("search/v1", "fetch/v2"),
            output_contract="结构化输出",
        )
        bytes_profile = build_baseline_profile(
            "baseline",
            "1",
            system_prompt="系统提示",
            workflow="节点甲 -> 节点乙".encode(),
            tool_contract_ids=("fetch/v2", "search/v1"),
            output_contract="结构化输出".encode(),
        )
        self.assertEqual(text_profile, bytes_profile)
        self.assertTrue(text_profile.output_contract_hash)

    def test_generic_token_estimator_handles_multilingual_content(self) -> None:
        estimator = Utf8TokenEstimator()
        self.assertGreater(estimator.estimate("structured output 结构化输出"), 0)
        self.assertEqual(estimator.estimate(""), 0)

    def test_benefit_policy_aggregates_multiple_domains_and_explains_rejection(self) -> None:
        measurements = tuple(
            measure_benefit(
                experience_id="exp",
                revision_id="rev",
                baseline_id="baseline",
                run_id=run_id,
                quality_delta=quality,
                success_rate_delta=success,
                input_token_delta=tokens,
                output_token_delta=0,
                latency_ms_delta=0,
                mining_tokens=0,
                mining_latency_ms=0,
                expected_reuse_count=10,
                sample_count=samples,
                token_cost_weight=0,
                latency_cost_weight=0,
            )
            for run_id, quality, success, tokens, samples in (
                ("code-generation", 2.0, 0.1, 20, 3),
                ("support-routing", -2.0, -0.2, 20, 3),
            )
        )
        aggregate = BenefitAggregate.from_measurements(measurements)
        decision = BreakEvenPolicy(minimum_measurements=2).evaluate(aggregate)
        self.assertFalse(decision.accepted)
        self.assertIn("success_rate_regressed", decision.reasons)
        self.assertEqual(decision.policy_version, "1")

    def test_miner_is_baseline_relative_and_model_free(self) -> None:
        baseline = build_baseline_profile(
            "structured-output", "1", system_prompt="return valid output", model_id="model-x"
        )
        runs = (
            RunFeatures(
                "run-a",
                frozenset({"schema_valid", "source_citations"}),
                tool_sequence=("fetch", "verify"),
            ),
            RunFeatures(
                "run-b",
                frozenset({"schema_valid", "source_citations", "extra"}),
                tool_sequence=("fetch", "verify"),
            ),
        )
        result = DeterministicMiner().mine(
            baseline, runs, baseline_constraints=frozenset({"schema_valid"})
        )
        self.assertFalse(result.used_llm)
        self.assertEqual(result.mining_input_tokens, 0)
        self.assertEqual(result.mining_output_tokens, 0)
        self.assertGreaterEqual(result.mining_latency_ms, 0)
        paths = {rule.path for rule in result.delta.rules}
        self.assertIn("output.constraints.source_citations", paths)
        self.assertNotIn("output.constraints.schema_valid", paths)
        self.assertIn("workflow.tool_sequence", paths)
        definition = definition_from_delta(result, task_type="structured-output")
        self.assertEqual(definition.mining_latency_ms, result.mining_latency_ms)

    def test_selector_obeys_token_budget_and_baseline_dedup(self) -> None:
        baseline = build_baseline_profile("agent", "1")
        result = DeterministicMiner().mine(
            baseline,
            (
                RunFeatures("a", frozenset({"a", "b", "c"})),
                RunFeatures("b", frozenset({"a", "b", "c"})),
            ),
        )
        definition = definition_from_delta(result, task_type="generic")
        selection = RuleSelector().select(
            definition,
            TokenBudget(1000, 800, 100, max_experience_tokens=20),
            baseline_paths=frozenset({"output.constraints.a"}),
        )
        self.assertLessEqual(selection.estimated_tokens, 20)
        self.assertNotIn("constraint-1", {item.rule_id for item in selection.selected})

    def test_positive_benefit_activates_and_negative_quarantines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with Repository(Path(directory) / "repo") as repository:
                baseline = build_baseline_profile("workflow", "1")
                mined = DeterministicMiner().mine(
                    baseline,
                    (
                        RunFeatures("a", frozenset({"verified"})),
                        RunFeatures("b", frozenset({"verified"})),
                    ),
                )
                candidate = definition_from_delta(mined, task_type="generic")
                repository.append_event(
                    events_pb2.EXPERIENCE_CANDIDATE_CREATED,
                    run_id="a",
                    producer="test",
                    payload=candidate,
                )
                lifecycle = LifecycleManager(repository, PromotionPolicy(2, 99, 1, True))
                validated = lifecycle.transition(candidate, experience_pb2.VALIDATED)
                positive = measure_benefit(
                    experience_id=validated.experience_id,
                    revision_id=validated.revision_id,
                    baseline_id="workflow",
                    run_id="holdout",
                    quality_delta=10,
                    success_rate_delta=0.1,
                    input_token_delta=20,
                    output_token_delta=-100,
                    latency_ms_delta=-200,
                    mining_tokens=0,
                    mining_latency_ms=0,
                    expected_reuse_count=100,
                    sample_count=3,
                )
                BenefitLedger(repository).record(positive)
                policy = BreakEvenPolicy(minimum_quality_delta=1, minimum_holdout_samples=2)
                active = lifecycle.promote_with_benefit(
                    candidate.experience_id, policy, manual_approval=True
                )
                self.assertEqual(active.status, experience_pb2.ACTIVE)
                negative = measure_benefit(
                    experience_id=active.experience_id,
                    revision_id=active.revision_id,
                    baseline_id="workflow",
                    run_id="production",
                    quality_delta=-1,
                    success_rate_delta=-0.1,
                    input_token_delta=500,
                    output_token_delta=100,
                    latency_ms_delta=1000,
                    mining_tokens=0,
                    mining_latency_ms=0,
                    expected_reuse_count=100,
                    output_truncated=True,
                )
                BenefitLedger(repository).record(negative)
                quarantined = lifecycle.enforce_benefit(candidate.experience_id, policy)
                self.assertEqual(quarantined.status, experience_pb2.QUARANTINED)


if __name__ == "__main__":
    unittest.main()
