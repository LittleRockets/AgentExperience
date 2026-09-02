# Adaptive Selection v0.3

AgentExperience v0.3 selects experience as bounded advice. It does not edit prompts, invoke tools,
change retry limits or otherwise control a Harness.

## Policy Object v1

`PolicyObject` is an immutable, versioned view of one experience revision. It contains trigger and
precondition rules, environment and capability requirements, expected effect, evidence, explicit
cost and risk, a validity window and an optional declarative Policy Delta. `canonical_json()` and
`revision_hash` make the exact policy used by a decision reproducible. Existing Protobuf
`ExperienceDefinition` revisions migrate through `policy_from_definition()` without changing the
stored event log.

The precondition language is deliberately non-executable: `key`, `key=value` and `key!=value`.
Unknown risk is ordered above high risk and therefore fails a default medium-risk budget.

## Selection pipeline

`AdaptiveSelector.select()` executes a stable sequence:

1. Bound and deterministically order candidates.
2. Enforce TTL, task type, framework, tool, capability, environment, precondition, risk, cost and
   confidence constraints.
3. Score surviving candidates as applicability, expected benefit, cost, risk and uncertainty.
4. Fall back to the deterministic scorer if a configured scorer raises an exception.
5. Apply a deterministic tie-break and explicit abstention.
6. Compose only policies that mutually opt in, do not explicitly conflict and do not write the same
   Policy Delta path.

Soft scores are never allowed to override a hard constraint. A shadow scorer can be evaluated and
recorded without affecting the returned decision.

```python
from agent_experience import (
    AdaptiveSelector,
    PolicyObject,
    RiskLevel,
    SelectionContext,
)

context = SelectionContext(
    task="debug the failing test",
    task_type="debug",
    available_tools=frozenset({"shell"}),
    max_prompt_tokens=64,
    max_risk=RiskLevel.MEDIUM,
)
result = AdaptiveSelector().select((policy,), context)
```

`ExperienceRun.select()` uses this contract before rendering the existing budgeted v0.2 Policy
Delta. Returned `SelectionResult.steps` remain suggestions and include
`HARNESS_ADOPTION_REQUIRED`. Adoption is only recorded after the Harness explicitly calls
`feedback(..., accepted=True)`.

## Feedback and evaluation

`DriftMonitor` produces a non-mutating quarantine recommendation using recent decay, environment
cohorts, selector versions, negative transfer and paired reward deltas. Lifecycle mutation remains
an explicit operator action.

`evaluate_selection()` reports selection precision, negative transfer, coverage, abstention
quality, expected calibration error, paired net benefit and a confidence interval. It rejects the
claim that an evaluation is leakage-free when sample, source or task fingerprints cross
train/dev/holdout boundaries.

Run the reproducible synthetic reference benchmark with:

```powershell
$env:PYTHONPATH = "src"
python tools/adaptive_selection_effects.py --samples 100
```

The benchmark is a contract and safety check, not evidence of real-world model improvement. A
production release decision still requires independently sourced holdout tasks and validated
counterfactual outcomes.

## Security and compatibility

- Only ACTIVE definitions enter the Runtime selection path.
- Candidate content never bypasses tool, capability, cost or risk budgets.
- Scorers cannot bypass hard constraints.
- Composition is bounded and deny-by-default.
- Selection traces persist selector version, policy hash, decision and reason codes.
- V0.2 sessions, decorators, repositories, packages and adapters remain supported.
