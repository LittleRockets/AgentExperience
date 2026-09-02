# AgentExperience v0.3.0

Release date: 2026-08-21

V0.3.0 upgrades selection from similarity-ranked recall to deterministic, evidence-aware adaptive
advice while preserving the Harness ownership boundary introduced in v0.2.

## Highlights

- Added immutable Policy Object v1 with canonical JSON, revision hashes, validity windows,
  preconditions, capability/environment requirements, expected effect, cost, risk and confidence.
- Added a deterministic selection pipeline with hard constraints, decomposed scores, stable
  tie-breaks, explicit rejection reasons and ABSTAIN.
- Added a pluggable scorer contract with deterministic fallback and non-interfering shadow scores.
- Added bounded composition with mutual opt-in, explicit conflicts and Policy Delta path collision
  detection.
- Added recent-decay drift reports by cohort and selector version with non-mutating quarantine
  recommendations.
- Added leakage checks and offline metrics for precision, negative transfer, coverage, abstention,
  calibration and paired net benefit confidence intervals.
- Integrated v0.3 ranking into `ExperienceRun.select()` while retaining token-bounded v0.2 Policy
  Delta rendering and explicit Harness adoption.

## Compatibility and safety

The existing `SelectionResult` shape and all v0.2 session methods remain source compatible.
`PROTOCOL_API_VERSION` is now `0.3`; existing adapter capability declarations and v0.2 conformance
schema remain valid. Repository and package schemas do not require a destructive migration.

No policy is automatically applied. High/unknown risk, expired policies, missing capabilities,
failed preconditions and exceeded budgets fail closed before any scorer runs.

## Verification

The release gate passed Ruff, strict MyPy over 56 source files, 79 Pytest cases, sdist/wheel build,
Twine checks and a wheel-installed Custom/LangGraph/Codex-like Loop smoke. The synthetic adaptive
selection reference benchmark also passed determinism and hard-constraint checks; it is not a
production effectiveness claim. Artifact digests are recorded in the release handoff rather than
inside the artifacts themselves.

## Installation

```powershell
pip install agent-experience==0.3.0
```

See [Adaptive Selection v0.3](adaptive-selection-v0.3.md) for the contracts and evaluation limits.
