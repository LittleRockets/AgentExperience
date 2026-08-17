# API guide

This guide documents the intended public surface exported by `agent_experience` and
`agent_experience.adapters`. Protobuf classes under `agent_experience.schema` are public data
contracts but are lower-level and may evolve during pre-alpha development.

## Primary Runtime API

### `agent_experience(path=".agent-experience", *, redaction=None, minimum_confidence=0.8)`

Creates the single path-scoped `ExperienceRuntime`. This factory is the recommended application
entry point.

### `ExperienceRuntime.run`

Supports both `@experience.run` and `@experience.run(verify=predicate)`. It automatically records a
run boundary and preserves synchronous/asynchronous return and exception behavior. A verifier emits
quality evidence once for the complete causal run tree; without it, the trace remains observational.

### `ExperienceRuntime.tool`

Used as bare `@experience.tool`. It derives a contract identity from Python module, qualified name,
signature and code fingerprint. Nested tools reuse the active run context; standalone calls receive
an automatic run. It does not require a path, name, registry or ToolSpec.

The same decorator is used for application Skills. A Skill is treated as a callable capability
boundary; its module, qualified name, signature and code fingerprint provide the automatic identity
and implementation version. AgentExperience observes execution evidence but never persists or
executes the Skill's source code.

### `ExperienceRuntime.langchain()` / `langgraph()` / `mcp()`

These methods bind optional framework integrations to the runtime-owned instrumentation gateway.
They never require another storage path or Repository:

- `langchain()` returns middleware for the framework's `middleware` list;
- `langgraph(run_id=None)` returns a bridge for typed graph stream events;
- `mcp(session, trust_domain=..., transport_identity="")` returns an observed client-session proxy.

Framework-native registration is still explicit because silently monkey-patching framework objects
would be unsafe and version-fragile.

### Portable package API

`ExperienceRuntime.mount(reference, *, sha256="", bindings=None) -> MountReport` resolves a local
path or HTTPS package, verifies its bounded v1/v2 container, checks signature/trust and compatibility,
deduplicates content and imports new revisions in quarantine.

`inspect_package(reference, *, sha256="") -> PackageInspection` performs the same package, source
and security checks without changing the mount catalog. `mounts()` returns the selected generation
for every logical package.

`validate_mount(name, verifier, *, max_runs=6)` runs bounded, caller-controlled local definition
validation. Packages never carry executable verifiers.

`upgrade_mount(name, reference)`, `rollback_mount(name)` and `unmount(name)` provide auditable,
reversible lifecycle operations. New generations do not replace the old view until mounting commits.

`export(destination, *, name, version, publisher="", signer=None)` exports only validated/active
definitions as a deterministic v2 package. Source/evidence run IDs are removed and secret-like
content is rejected.

`ExperienceRuntime.trust` exposes the repository-local `TrustStore` for Ed25519 public keys.
`MountPolicy` centralizes unsigned/legacy acceptance, size, compression, network and offline limits.

Public result/status types are `PackageInspection`, `MountReport`, `MountStatus`, `TrustStatus`,
`CompatibilityStatus`, `CapabilityBinding` and `ReasonCode`.

### `ExperienceRuntime.flush()` / `close()`

`flush()` waits for background candidate consolidation and surfaces worker failures. `close()`
flushes, stops the worker and closes storage. The runtime also registers a process-exit close hook.

### `ExperienceRuntime.repository`

Advanced read/export escape hatch for the runtime-owned Repository. Normal observation code should
not access it.

Everything below is the low-level or policy surface used to extend the Runtime.

## Storage and observation

### `Repository(path, *, durability=...)`

Owns the append-only event log. Use it as a context manager. Important methods:

- `append_event(...)`: append a typed event with run/correlation/causation metadata;
- `events()`: iterate verified event envelopes;
- `verify()`: verify framing, checksums, repository identity and sequence ordering;
- `last_sequence`: current sequence number.

The built-in repository is single-process/single-writer.

### `capture(repository, *, producer, evaluator, redaction)`

Decorator for synchronous or asynchronous Python functions. It records run boundaries while
preserving the wrapped function's result and exception behavior.

### `ObservationContext`

Carries `run_id`, `correlation_id` and `causation_id` through nested model/tool calls.
`current_context()` returns the current context.

### `ToolRegistry`, `ToolSpec`

Explicit registry for known typed tools. Replay resolves only registered contracts; arbitrary
callables or code from stored experience are never executed.

### `RedactionPolicy`

Sanitizes observed mappings, sequences, strings and objects. Applications can inject a stricter
policy at observation boundaries.

## Outcome evaluation

### `Outcome`

Enum: `SUCCESS`, `FAILURE`, `PARTIAL`, `UNKNOWN`.

### `Evaluation`

Immutable result containing outcome, confidence, evaluator ID/version and evidence references.

### `OutcomeEvaluator[T]`

Protocol for custom deterministic or externally verified evaluators.

### `PredicateEvaluator[T]`

Convenience evaluator backed by a predicate. Prefer stable, versioned predicates over model
self-grading for activation evidence.

## Extraction, mining and lifecycle

### `CandidateService(repository, *, minimum_confidence=0.8)`

`extract_all()` rebuilds traces, extracts eligible candidates and deduplicates semantic content.

### `RunFeatures`

Compact normalized evidence: passed/failed constraints, optional tool sequence, tokens and latency.
It intentionally excludes the original model output.

### `build_baseline_profile(...)`

Creates a versioned fingerprint of the system prompt, workflow, sorted tool contracts, output
contract and model identity. Text is normalized as UTF-8; workflow/output contracts accept `str`
or `bytes`.

### `DeterministicMiner`

`mine(baseline, runs, baseline_constraints=...)` intersects facts from at least two independent
runs, removes baseline facts and returns `MiningResult`. The built-in miner uses no LLM tokens.

### `MiningResult`

Contains the `ExperienceDelta`, source run IDs, whether an LLM was used, mining input/output tokens
and mining latency.

### `definition_from_delta(result, *, task_type, created_by=...)`

Creates an immutable Candidate `ExperienceDefinition` in `PROMPT_DELTA` mode.

### `PromotionPolicy`

Configures independent success/failure thresholds and manual approval requirements.

### `LifecycleManager`

- `record_evaluation(evaluation)` appends evidence;
- `promote(experience_id, manual_approval=False)` applies evidence thresholds;
- `promote_with_benefit(...)` activates a Validated revision only after benefit acceptance;
- `enforce_benefit(...)` quarantines Active/Validated revisions that fail aggregate policy;
- `transition(current, status)` creates a legal immutable revision.

### `ExperienceCatalog`

Rebuilds current definitions and evaluation evidence from the event log.

## Rule selection and extension protocols

### `TokenBudget`

Defines total context, base input, reserved output and maximum experience tokens.
`available_experience_tokens` is the usable minimum after all constraints.

### `RuleSelector`

Selects highest-priority `PROMPT_DELTA` rules that are not already represented by baseline paths and
fit the budget. `select_and_record()` also emits an auditable selection/rejection event.

### `RuleSelection`

Contains selected rules, rejected IDs, estimated tokens and rendered text.

### `FeatureExtractor[T]`

Protocol for mapping a framework/domain run into `RunFeatures`.

### `BaselineResolver[T]`

Protocol for resolving application state into a `BaselineProfile`.

### `TokenEstimator`

Protocol for model-aware token estimation. `Utf8TokenEstimator` is the dependency-free fallback,
not an exact tokenizer.

## Benefit accounting

### `measure_benefit(...)`

Builds a `BenefitMeasurement` from A/B or controlled comparison deltas. Mining cost is amortized by
expected reuse count before computing net benefit.

### `BenefitLedger`

- `record(measurement)` appends a measurement;
- `measurements(experience_id)` reads raw measurements;
- `aggregate(experience_id, revision_id=None, window=None)` returns a sample-weighted aggregate.

### `BenefitAggregate`

Revision-scoped weighted means for quality, success, tokens, latency and net benefit, plus sample,
measurement and truncation counts.

### `BreakEvenPolicy`

Versioned, configurable thresholds. `evaluate(aggregate)` returns `BenefitDecision`;
`accepts(measurement)` remains a single-measurement compatibility helper.

### `BenefitDecision`

Contains policy identity/version, acceptance status, machine-readable rejection reasons and the
evaluated aggregate.

## Retrieval and advice

### `RetrievalQuery`

Text plus optional task type, framework, available tools, result limit and minimum score.

### `ExperienceRetriever`

Searches only Active and applicable definitions, then performs deterministic lexical ranking with
an evidence contribution.

### `Advice`

Source-attributed untrusted reference with experience/revision IDs, score, source runs and optional
registered-tool steps.

### `AdviceBudget`, `render_semantic_advice(...)`

Compatibility helpers for bounding legacy semantic summaries. New efficient integrations should
prefer structured delta rules and `RuleSelector`.

## Replay and package exchange

### `validate_dag(strategy)`

Validates node identities, dependencies and cycles before execution.

### `ReplayExecutor`

Executes a validated strategy using the explicit `ToolRegistry`, approval policy, retries and a
caller-provided verifier. See class signatures/type hints for construction details.

### `export_package(repository, destination, *, publisher="")`

Exports eligible definitions to a checksummed `.exp` package.

### `import_package(repository, source)`

Validates bounds/checksums and imports definitions as Quarantined, with deduplication.

## Optional adapters

Import these from `agent_experience.adapters`:

- `create_langchain_middleware(repository, ...)`;
- `LangGraphEventBridge(repository, ...)`;
- `create_langgraph_callback(bridge)`;
- `ObservedClientSession(session, repository, trust_domain=..., ...)`;
- `MCPServerIdentity`;
- `wrap_agent(...)`, `WrappedAgent` and capability declarations.

Optional framework imports are delayed. If an extra is missing, the factory raises an `ImportError`
with the required install command instead of breaking core package import.

## CLI

`agent-exp --version` prints the installed version. Subcommands are `inspect`, `verify`, `extract`,
`candidates`, `benefits`, `export`, and `import`. Run `agent-exp COMMAND --help` for arguments.
# Experience Protocol (v0.2 preview)

External Harnesses should use an explicit run session while retaining ownership of their Loop:

```python
from agent_experience import (
    HarnessState,
    Outcome,
    RunOutcome,
    RuntimeEvent,
    agent_experience,
)
from agent_experience.schema import events_pb2

experience = agent_experience("./experience-data")
run = experience.start(
    "repair the failing test",
    agent="coding-agent",
    harness="custom-loop",
    task_id="issue-42",
    tools=("python://tests", "python://editor"),
)
run.observe(RuntimeEvent(events_pb2.NODE_STARTED, {"node_id": "inspect"}))
selection = run.select(HarnessState(task="repair the failing test"))
run.feedback(RunOutcome(Outcome.UNKNOWN, metrics={"attempt": 1.0}))
run.complete(RunOutcome(Outcome.SUCCESS, result={"fixed": True}))
```

The session is terminal after `complete()` or `cancel()`. Later operations raise `RuntimeError`
rather than silently appending invalid evidence. Selection returns advice or an explicit abstention;
the Harness remains responsible for planning, execution, verification, retries and stopping.

An ACTIVE `PROMPT_DELTA` remains advice rather than executable control. Pass its applicability and
budget through the frozen v0.2 extension maps, then explicitly adopt and report the decision:

```python
state = HarnessState(
    task="plan a two-day New York trip",
    harness_policy={"task_type": "travel_plan", "baseline_paths": ()},
    budget={
        "max_context_tokens": 8192,
        "base_input_tokens": 100,
        "reserved_output_tokens": 3000,
        "max_experience_tokens": 96,
    },
)
result = run.select(state)[0]
if result.decision.value == "selected":
    # The Harness may place result.steps in its own bounded prompt/control surface.
    run.feedback(
        RunOutcome(Outcome.UNKNOWN),
        experience_id=result.experience_id,
        revision_id=result.revision_id,
        accepted=True,
    )
```

Only ACTIVE and applicable definitions are considered. A Policy Delta without an explicit token
budget is rejected with `MISSING_TOKEN_BUDGET`; a budget that fits no rules is rejected with
`POLICY_DELTA_BUDGET_EXHAUSTED`. Selected rules carry `HARNESS_ADOPTION_REQUIRED`: the Runtime never
injects them or records application on its own. Quarantined, validated, candidate and deprecated
definitions remain unavailable to this path.

Use `run.start_child(task)` for delegation. The child inherits the parent agent, Harness, model,
environment, budget and tool snapshot unless explicitly overridden, and stores `parent_run_id` for
auditable lineage. `ExperienceRuntime.active_run_count` is intended for diagnostics. Runtime shutdown
records `RUN_CANCELLED` for every unfinished explicit session before closing storage.

Third-party integrations can add a persisted-evidence conformance test:

```python
from agent_experience import run_protocol_conformance

report = run_protocol_conformance(experience, "my-harness", exercise_one_run)
assert report.passed, report.checks
```

The exercise callback receives the Runtime, performs one complete or cancelled task, and returns its
run ID. The report verifies lifecycle cardinality, terminal ordering, correlation and payload
integrity. It uses `PASS`, `FAIL`, `UNSUPPORTED` and `INCONCLUSIVE` statuses so future adapter-specific
checks can describe partial framework capabilities without claiming success.

## Adapter capability declarations

`AdapterCapabilities` now declares `protocol_version` plus support for explicit runs, selection,
feedback, delegation and async execution. Dependencies fail closed: an adapter cannot claim feedback
or delegation unless it also supports explicit runs. Pass the declaration and
`ConformanceRequirements` to `run_protocol_conformance()` when an integration promises optional
capabilities.

`UNSUPPORTED` means the adapter explicitly declares that a required feature is unavailable.
`INCONCLUSIVE` means the capability was required but no machine-readable declaration was supplied.
Neither status counts as a passing report.

## Async semantics

The v0.2 protocol deliberately has one lifecycle model rather than separate sync and async state
machines. Async Harness tasks may call `start`, `observe`, `select`, `feedback` and `complete` at
their lifecycle boundaries. Session identity is explicit and does not depend on a shared mutable
current run. Local event persistence remains ordered and synchronous; the library does not wrap it
in hidden executor threads. A future asynchronous storage backend must preserve the same ordering,
terminal-state and cancellation contracts before adding awaitable persistence APIs.

## LangGraph explicit sessions

Pass an explicit protocol run to `ExperienceRuntime.langgraph(run=run)` to place normalized node,
route, checkpoint and interrupt evidence in the same lifecycle as selection and outcome feedback.
Passing both `run` and `run_id` is an error. A run-bound bridge cannot spoof another run ID or pass
repository durability/storage arguments through the adapter boundary.

When conformance requirements include selection, feedback or delegation, the suite now checks
persisted `protocol_operation` attributes and child `parent_run_id` evidence. A declaration that
claims support without observable evidence produces `FAIL`; an explicit unsupported declaration
produces `UNSUPPORTED`.

## Protocol compatibility snapshot

`PROTOCOL_API_VERSION` is `"0.2"`. Tests freeze the public protocol exports, dataclass field order
and lifecycle method parameters. Additive changes require an intentional snapshot review; removing,
renaming or reordering existing fields requires a documented compatibility decision and cannot be
merged as an incidental refactor.

## Machine-readable conformance reports

`ConformanceReport.to_dict()` and `to_json()` emit schema version `0.2`, integration identity, run
ID, overall pass state and ordered checks. Every non-pass check carries a stable
`ConformanceReasonCode`, including exercise exceptions, lifecycle cardinality, terminal ordering,
correlation, payload integrity, unsupported/undeclared capabilities and missing behavioral evidence.
JSON output is deterministically key-sorted and is suitable for CI artifacts; automation should use
`status` and `reason_code`, not parse human-readable `detail` text.

## Event forward compatibility

Known events may add payload fields because Struct consumers preserve unknown extensions. An event
type whose lifecycle semantics are unknown to the installed SDK is critical by default and is
rejected. A producer may preserve an informational extension event by setting the envelope attribute
`compatibility=optional`. Optional unknown events retain payloads and integrity hashes, survive
repository replay, and advance projection watermarks without changing known read-model state.

Do not mark an event optional if ignoring it could change authorization, lifecycle state, money,
external side effects, verification or safety decisions.
