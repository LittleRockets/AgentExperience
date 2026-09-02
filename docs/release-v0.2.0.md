# AgentExperience v0.2.0

Release date: 2026-08-17

AgentExperience v0.2.0 introduces the framework-neutral Experience Protocol for explicit Harness
integration. A Harness keeps ownership of planning, tools, retries, verification and stopping;
AgentExperience provides auditable runtime evidence, bounded experience selection and feedback.

## Highlights

- Added the explicit, thread-safe `ExperienceRun` lifecycle:
  `start → observe → select → feedback → complete/cancel`.
- Added immutable protocol contracts:
  `RunContext`, `RuntimeEvent`, `HarnessState`, `RunOutcome` and `SelectionResult`.
- Added active-session tracking, cancellation on Runtime shutdown, context-manager failure
  finalization and parent/child delegated-run lineage.
- Added deterministic selection results with `SELECTED`, `REJECTED` and `ABSTAINED` decisions,
  stable reason codes and persisted protocol-operation evidence.
- Connected ACTIVE `PROMPT_DELTA` experiences to the v0.2 selection path:
  - task applicability through `harness_policy.task_type`;
  - explicit Token budget enforcement;
  - bounded rules returned through `SelectionResult.steps`;
  - `HARNESS_ADOPTION_REQUIRED` to keep Loop ownership outside Runtime.
- Added fail-closed behavior for missing or insufficient Policy Delta budgets.
- Added framework-neutral conformance reports with `PASS`, `FAIL`, `UNSUPPORTED` and
  `INCONCLUSIVE` statuses and deterministic JSON output.
- Added Custom Loop, Codex-like Loop and explicit LangGraph session examples.
- Added wheel-installed protocol smoke tests and CI coverage.
- Added compatibility handling for unknown events: critical unknown events fail closed; explicitly
  optional unknown events remain integrity-protected and replayable.

## Compatibility and safety

- Existing decorator, package/mount, event-log, lifecycle and adapter APIs remain supported.
- Only `ACTIVE` and applicable experiences can be selected by the v0.2 protocol.
- `CANDIDATE`, `VALIDATED`, `QUARANTINED` and `DEPRECATED` experiences are not selected.
- Runtime never silently injects advice, changes a Harness prompt or takes control of a Loop.
- A Harness must explicitly adopt advice and call `feedback(..., accepted=True)` before an
  `EXPERIENCE_APPLIED` event is recorded.
- No automatic Policy Delta execution, Harness self-modification or remote service is included.

## Verification

The release was verified with:

- Ruff: passed;
- MyPy strict: passed for 52 source files;
- Pytest: 72 passed;
- wheel/protocol smoke: passed;
- active-session cleanup and event-integrity checks: passed;
- New York two-day travel A/B example: Baseline, legacy v0.1 advice and formal v0.2 protocol advice.

The v0.2 local protocol effect baseline measured a 3.102 ms p95 selection/run path on the
development Windows/Python 3.13 environment. This is a development baseline, not a cross-platform
SLA.

## Examples and reports

- `examples/custom_loop_protocol.py`
- `examples/codex_like_loop.py`
- `examples/new_york_version_comparison.py`
- `docs/v0.2-effect-report.md`
- `docs/v0.2-baseline-agentexperience-report.md`
- `docs/api-guide.md`
- `docs/tutorial.md`

Run the New York comparison with:

```powershell
$env:PYTHONPATH = "src"
python examples/new_york_version_comparison.py
```

The example requires the local DeepSeek demo credential described by
`examples/deepseek_demo_local.example.py`. Never commit the real credential file.

## Installation

```powershell
pip install agent-experience==0.2.0
```

## Known limitations

- v0.2 selection is deterministic and rule-based; it is not a learning or adaptive selection
  service.
- Policy Delta is returned as bounded advice. The calling Harness remains responsible for deciding
  how to apply it and for evaluating the resulting outcome.
- Effectiveness claims require paired real-task experiments, independently validated outcomes,
  multiple seeds/models and cost/risk accounting.
- Cross-platform performance and production SLA guarantees are not implied by the local baseline.

## Next step

v0.3 will focus on richer Selection Contracts, evidence-aware ranking, benefit/cost/risk-aware
abstention and improved retrieval diagnostics while preserving the v0.2 Loop-ownership boundary.
