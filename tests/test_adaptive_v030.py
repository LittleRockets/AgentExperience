from __future__ import annotations

import time
import unittest

from agent_experience import (
    AdaptiveDecision,
    AdaptiveSelector,
    DriftMonitor,
    ExpectedEffect,
    PolicyCost,
    PolicyObject,
    RiskLevel,
    ScoreComponents,
    SelectionContext,
    SelectionFeedback,
    SelectionObservation,
    SelectorConfig,
    evaluate_selection,
)


def policy(identity: str, **changes: object) -> PolicyObject:
    values: dict[str, object] = {
        "experience_id": identity,
        "revision_id": f"{identity}-rev",
        "summary": "debug failing tests by inspecting dependencies",
        "task_types": ("debug",),
        "trigger_keywords": ("debug", "tests"),
        "required_tools": frozenset({"shell"}),
        "expected_effect": ExpectedEffect(benefit=0.8, uncertainty=0.1),
        "cost": PolicyCost(prompt_tokens=20),
        "risk": RiskLevel.LOW,
        "confidence": 0.9,
        "evidence": ("run-1", "run-2"),
    }
    values.update(changes)
    return PolicyObject(**values)  # type: ignore[arg-type]


class BrokenScorer:
    scorer_id = "broken"
    version = "1"

    def score(self, policy: PolicyObject, context: SelectionContext) -> ScoreComponents:
        del policy, context
        raise RuntimeError("unavailable")


class AdaptiveV030Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = SelectionContext(
            task="debug the failing tests",
            task_type="debug",
            available_tools=frozenset({"shell"}),
            max_prompt_tokens=64,
            max_risk=RiskLevel.MEDIUM,
        )

    def test_policy_hash_is_canonical_and_validated(self) -> None:
        first = policy("a", environment={"os": "windows", "region": "cn"})
        second = policy("a", environment={"region": "cn", "os": "windows"})
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.revision_hash, second.revision_hash)
        with self.assertRaisesRegex(ValueError, "confidence"):
            policy("invalid", confidence=1.1)

    def test_hard_constraints_cannot_be_overridden_by_scoring(self) -> None:
        high_risk = policy("high", risk=RiskLevel.HIGH)
        expensive = policy("expensive", cost=PolicyCost(prompt_tokens=65))
        batch = AdaptiveSelector().select((high_risk, expensive), self.context)
        self.assertEqual(batch.decisions[0].decision, AdaptiveDecision.ABSTAINED)
        reasons = {reason for item in batch.decisions for reason in item.reason_codes}
        self.assertIn("RISK_BUDGET_EXCEEDED", reasons)
        self.assertIn("PROMPT_TOKEN_BUDGET_EXCEEDED", reasons)

    def test_order_is_deterministic_and_scorer_failure_falls_back(self) -> None:
        selector = AdaptiveSelector(scorer=BrokenScorer())
        first = selector.select((policy("b"), policy("a")), self.context)
        second = selector.select((policy("a"), policy("b")), self.context)
        self.assertEqual(first.selected[0].experience_id, "a")
        self.assertEqual(first.selected, second.selected)
        self.assertIn("SCORER_FAILED_SAFE_FALLBACK", first.selected[0].reason_codes)

    def test_composition_requires_mutual_declaration_and_distinct_paths(self) -> None:
        a = policy("a", composable_with=frozenset({"b"}), policy_delta={"retry.limit": 2})
        b = policy("b", composable_with=frozenset({"a"}), policy_delta={"verify.mode": "strict"})
        selector = AdaptiveSelector(SelectorConfig(max_composition=2))
        composed = selector.select((a, b), self.context, limit=2)
        self.assertEqual(composed.composite_experience_ids, ("a", "b"))
        conflict = policy("b", composable_with=frozenset({"a"}), policy_delta={"retry.limit": 3})
        not_composed = selector.select((a, conflict), self.context, limit=2)
        self.assertEqual(len(not_composed.selected), 1)

    def test_ttl_precondition_and_environment_fail_closed(self) -> None:
        expired = policy("expired", valid_until_ns=time.time_ns() - 1)
        conditional = policy("conditional", preconditions=("verified=true",))
        environment = policy("environment", environment={"os": "linux"})
        batch = AdaptiveSelector().select((expired, conditional, environment), self.context)
        reasons = {reason for item in batch.decisions for reason in item.reason_codes}
        self.assertIn("POLICY_NOT_CURRENT", reasons)
        self.assertIn("PRECONDITION_FAILED", reasons)
        self.assertIn("ENVIRONMENT_MISMATCH", reasons)

    def test_offline_evaluation_detects_leakage_and_reports_metrics(self) -> None:
        observations = (
            SelectionObservation("train-1", "train", "source-a", True, True, 0.9, 1, 0),
            SelectionObservation("h-1", "holdout", "source-h1", True, True, 0.8, 2, 1),
            SelectionObservation("h-2", "holdout", "source-h2", True, False, 0.7, 0, 1),
            SelectionObservation("h-3", "holdout", "source-h3", False, False, 0.0, 1, 1),
        )
        report = evaluate_selection(observations)
        self.assertTrue(report.leakage_free)
        self.assertAlmostEqual(report.selection_precision, 0.5)
        self.assertAlmostEqual(report.coverage, 2 / 3)
        leaked = observations + (
            SelectionObservation("h-4", "holdout", "source-a", False, False, 0, 0, 0),
        )
        self.assertFalse(evaluate_selection(leaked).leakage_free)

    def test_recent_decay_drift_recommends_quarantine_without_mutating(self) -> None:
        now = time.time_ns()
        feedback = tuple(
            SelectionFeedback("a", "a-rev", "0.3.0", "windows", False, -1, now - index)
            for index in range(10)
        )
        report = DriftMonitor().evaluate(feedback, now_ns=now)
        self.assertTrue(report.quarantine_recommended)
        self.assertIn("NEGATIVE_TRANSFER_THRESHOLD_EXCEEDED", report.reason_codes)


if __name__ == "__main__":
    unittest.main()
