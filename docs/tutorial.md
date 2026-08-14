# AgentExperience tutorial

This tutorial starts with the decorator Runtime used by most applications. The lower-level pipeline
is documented afterward for storage/backend authors and advanced integrations.

## 1. Install

```bash
python -m venv .venv
```

On Windows:

```powershell
.venv\Scripts\python.exe -m pip install agent-experience
```

On macOS or Linux:

```bash
.venv/bin/python -m pip install agent-experience
```

Optional integrations are separate so the core remains lightweight:

```bash
pip install "agent-experience[langchain,langgraph,mcp]"
```

## 2. Recommended API: one path, two decorators

```python
from agent_experience import agent_experience

experience = agent_experience("./experience-data")

@experience.tool
def search(query: str) -> dict[str, object]:
    return {"query": query, "matches": 3}

@experience.run(verify=lambda result: result["matches"] > 0)
def agent(query: str) -> dict[str, object]:
    return search(query)

agent("runtime architecture")
```

The Runtime automatically owns the repository, identities, run context, causation, redaction,
timing, exception events and background candidate consolidation. The path is declared once. Tool
names, contracts and experience rule paths are generated internally.

`verify` belongs only on the outer run. Without it, execution is still observed but cannot produce
quality evidence for an activatable experience. In tests and short-lived scripts, call
`experience.flush()` before inspecting candidates. `experience.close()` flushes and closes storage;
long-running applications are also protected by an exit hook.

### Observe a Skill

AgentExperience does not impose a vendor-specific Skill format. Decorate the public callable of any
reusable capability with `@experience.tool`, then verify quality once at the surrounding task:

```python
@experience.tool
def document_skill(document: str) -> dict[str, object]:
    result = existing_skill.run(document)
    return {"content": result, "passed_checks": validate(result)}

@experience.run(verify=lambda result: bool(result["passed_checks"]))
def document_agent(document: str) -> dict[str, object]:
    return document_skill(document)
```

The Skill receives an automatic identity and code-version fingerprint. Its source code is not stored
as experience.

## 3. Portable experience packages

### Mount in one line

```python
report = experience.mount("./shared.exp")
print(report)
```

`MountReport` shows identity/version, digest, publisher trust, imported/duplicate counts, compatible
experiences, missing bindings and a machine-readable reason. Mounting never activates external
experience: imported revisions are quarantined and replay/cache permissions are disabled.

Mount several packages after Tools and Skills register automatically:

```python
experience = agent_experience(
    "./experience-data",
    experiences=["./team.exp", "./organization.exp"],
)
```

### Stable capability binding

Most applications keep the bare decorator. Authors who publish a capability across projects can add
one portable contract without supplying storage paths or internal IDs:

```python
@experience.tool(capability="weather/current-conditions@1")
def get_weather(city: str):
    return weather_client.get(city)
```

Exact portable contracts bind automatically. Missing or ambiguous capabilities stay in
`NEEDS_BINDING` and are never silently selected.

### Trust and local validation

```python
public_key = Path("publisher-public.key").read_bytes()
experience.trust.add(public_key, alias="team-publisher")

report = experience.validate_mount(
    "team-patterns",
    verifier=lambda definition: run_local_contract_tests(definition),
    max_runs=6,
)
```

Publisher trust and local validity are separate. Signing proves origin; the receiving application
decides correctness. Packages never carry executable verifiers.

### Export, upgrade, rollback and unmount

```python
experience.export(
    "team-patterns.exp",
    name="team-patterns",
    version="1.0.0",
    signer=signer,
)

experience.upgrade_mount("team-patterns", "./team-patterns-1.1.0.exp")
experience.rollback_mount("team-patterns")
experience.unmount("team-patterns")
```

Operations are append-only and auditable. Upgrade failure leaves the selected generation unchanged;
unmount disables package revisions without erasing their audit trail.

The remaining sections describe advanced low-level APIs. Most users do not need them.

## 4. Low-level capture and outcomes

Completion is an observation; success is an evaluation. Supply a stable evaluator ID/version and
deterministic evidence whenever possible.

```python
from pathlib import Path

from agent_experience import PredicateEvaluator, Repository, capture

repository_path = Path("experience-data")

with Repository(repository_path) as repository:
    evaluator = PredicateEvaluator(
        lambda value: value.startswith("verified:"),
        evaluator_id="verified-prefix",
        evaluator_version="1",
    )

    @capture(repository, evaluator=evaluator, producer="my-agent/v1")
    def run_agent(task: str) -> str:
        return f"verified:{task}"

    run_agent("example")
    print(repository.verify())
```

The decorator preserves return values and exceptions. Synchronous and asynchronous functions are
supported. A default redaction policy sanitizes observed values; applications should still avoid
passing secrets into model/tool payloads unnecessarily.

## 5. Low-level candidate extraction

```python
from agent_experience import CandidateService, Repository

with Repository(repository_path) as repository:
    candidates = CandidateService(repository, minimum_confidence=0.8).extract_all()
```

Extraction is deduplicated by semantic content hash. A successful run can create a candidate, but
cannot make it active by itself.

## 6. Mine a minimal baseline-relative delta

An application adapter converts verified runs into generic feature paths. These names are owned by
the application or integration—not by the core library.

```python
from agent_experience import (
    DeterministicMiner,
    RunFeatures,
    build_baseline_profile,
    definition_from_delta,
)

baseline = build_baseline_profile(
    "support-agent",
    "2026-08-14",
    system_prompt="Follow the support policy.",
    tool_contract_ids=("crm.lookup/v1",),
    output_contract="Return a validated response object.",
    model_id="model-family/version",
)

runs = (
    RunFeatures("run-1", frozenset({"schema_valid", "policy_cited"})),
    RunFeatures("run-2", frozenset({"schema_valid", "policy_cited"})),
)

mined = DeterministicMiner().mine(
    baseline,
    runs,
    baseline_constraints=frozenset({"schema_valid"}),
)
candidate = definition_from_delta(mined, task_type="support")
```

The deterministic miner does not call an LLM. It intersects facts from independent successful
runs, removes baseline facts and records mining token/latency cost.

## 7. Select rules within a token budget

```python
from agent_experience import RuleSelector, TokenBudget

budget = TokenBudget(
    max_context_tokens=8_192,
    base_input_tokens=2_000,
    reserved_output_tokens=2_000,
    max_experience_tokens=128,
)
selection = RuleSelector().select(
    candidate,
    budget,
    baseline_paths=frozenset({"output.constraints.schema_valid"}),
)

print(selection.rendered)
print(selection.rejected_rule_ids)
```

Only `PROMPT_DELTA` rules are rendered by `RuleSelector`. Inject the selected text as subordinate,
untrusted guidance; it must not override system, security or permission policy. For model-accurate
token counts, implement the `TokenEstimator` protocol with the model's tokenizer.

## 8. Measure benefit before activation

```python
from agent_experience import BenefitLedger, BreakEvenPolicy, measure_benefit

measurement = measure_benefit(
    experience_id=candidate.experience_id,
    revision_id=candidate.revision_id,
    baseline_id=baseline.baseline_id,
    run_id="holdout-1",
    quality_delta=0.08,
    success_rate_delta=0.03,
    input_token_delta=42,
    output_token_delta=-20,
    latency_ms_delta=120,
    mining_tokens=mined.mining_input_tokens + mined.mining_output_tokens,
    mining_latency_ms=mined.mining_latency_ms,
    expected_reuse_count=100,
    sample_count=25,
)

policy = BreakEvenPolicy(
    minimum_measurements=3,
    minimum_holdout_samples=50,
    maximum_input_token_increase=128,
    policy_id="support-production",
    policy_version="1",
)

with Repository(repository_path) as repository:
    ledger = BenefitLedger(repository)
    ledger.record(measurement)
    aggregate = ledger.aggregate(candidate.experience_id, revision_id=candidate.revision_id)
    decision = policy.evaluate(aggregate)
    print(decision.accepted, decision.reasons)
```

Choose quality/token/latency weights before seeing experiment results. Do not tune policy values to
make a benchmark look positive. Aggregate only comparable trials and keep training evidence separate
from holdout or production evidence.

## 9. Lifecycle

`LifecycleManager` creates immutable revisions. Default transitions include:

```text
CANDIDATE → VALIDATED → ACTIVE → DEPRECATED
     │           │          │
     └───────────┴──────────┴→ QUARANTINED
```

Use `promote()` for evidence thresholds and `promote_with_benefit()` to require an acceptable
revision-scoped benefit aggregate. Manual approval is required for activation by default.

## 10. Framework adapters

### LangChain

```python
from agent_experience.adapters import create_langchain_middleware

middleware = create_langchain_middleware(repository)
# Pass `middleware` through LangChain's public agent middleware API.
```

It observes agent, model and tool lifecycle hooks. Your application still supplies outcome quality.

### LangGraph

```python
from agent_experience.adapters import LangGraphEventBridge

bridge = LangGraphEventBridge(repository)
for event in graph.stream(inputs, stream_mode=["tasks", "updates"]):
    bridge.consume(event)
```

The bridge normalizes task/node, route, checkpoint, interrupt and resume events. Adapt the stream
loop to the exact LangGraph public API version installed in your application.

### MCP

```python
from agent_experience.adapters import ObservedClientSession

observed = ObservedClientSession(
    session,
    repository,
    trust_domain="internal-tools",
    transport_identity="stdio:approved-server",
)
await observed.initialize()
result = await observed.call_tool("search", {"query": "example"})
```

MCP content is untrusted. The proxy observes server identity, advertised capabilities and public
client operations; it does not grant replay permission.

## 11. Inspect and export

```bash
agent-exp verify experience-data
agent-exp inspect experience-data
agent-exp benefits experience-data
agent-exp export experience-data reviewed.exp
```

Import always quarantines experience for local review:

```bash
agent-exp import another-repository reviewed.exp
```

## 12. Production checklist

- Pin the package version and back up the event directory.
- Give every evaluator, baseline, tool contract and policy an explicit version.
- Redact secrets before they reach observation boundaries.
- Separate training, holdout and production measurements.
- Activate only immutable revisions with sufficient independent evidence.
- Enforce context and experience token budgets.
- Treat advice and imported packages as untrusted data.
- Register replayable tools explicitly and require approval/verifiers.
- Monitor benefit and quarantine regressions.
- Use an external backend before requiring multi-process or distributed writes.

## 13. Run the transparent DeepSeek demo

The example is deliberately verbose and incurs model API charges. It makes seven model calls: three
independent evidence runs, an Austria A/B holdout, and a Germany A/B generalization test. Experience
mining is deterministic and consumes no LLM tokens.

```powershell
Copy-Item examples\deepseek_demo_local.example.py examples\deepseek_demo_local.py
# Put the key in the ignored copy, never in the example template.
python examples\deepseek_experience_demo.py
```

Each run creates `demo-output/<timestamp>/full-comparison.md` and `report.json`. A failed Austria
comparison does not stop the Germany comparison; the final lifecycle decision uses the aggregate.
