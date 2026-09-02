# Changelog

All notable changes will be documented in this file.

## Unreleased

## 0.3.0 - 2026-08-21

### Added

- Add immutable Policy Object v1 contracts with canonical serialization, revision hashing,
  migration from legacy definitions, validity, evidence, cost, risk and advisory Policy Delta.
- Add deterministic adaptive selection with capability/environment/TTL/precondition hard filters,
  decomposed benefit/cost/risk/uncertainty scores, stable tie-breaks and explicit ABSTAIN.
- Add pluggable and shadow scorer contracts with safe deterministic fallback; soft scores cannot
  bypass hard constraints.
- Add bounded, mutual-opt-in composition with explicit conflicts and Policy Delta path collision
  detection.
- Add recent-decay, cohort-aware drift reports and selector-version comparison without automatic
  lifecycle mutation.
- Add leakage-aware offline evaluation for precision, negative transfer, coverage, abstention
  quality, calibration and paired net-benefit confidence intervals.
- Integrate v0.3 ranking and auditable policy hashes/reason traces into the explicit run selection
  path.
- Add a four-arm DeepSeek comparison using one no-experience Baseline and frozen v0.1, v0.2 and
  current v0.3 experience paths, with transport retries and explicit interpretation limits.

### Compatibility

- Preserve the v0.2 `SelectionResult` shape and explicit ExperienceRun lifecycle.
- Preserve budgeted Policy Delta advice and require explicit Harness adoption; v0.3 never controls
  or mutates a Harness.
- Reuse existing repository/package schemas and migrate definitions in memory without destructive
  storage changes.

## 0.2.0 - 2026-08-17

### Added

- Start the v0.2 Experience Protocol with explicit, thread-safe `ExperienceRun` sessions.
- Add immutable `RunContext`, `RuntimeEvent`, `HarnessState`, `RunOutcome` and explainable
  `SelectionResult` contracts.
- Add `ExperienceRuntime.start()` plus `observe()`, `select()`, `feedback()`, `complete()` and
  `cancel()` session operations for framework-neutral Harness integration.
- Add safe `ABSTAINED` selection results when no ACTIVE experience satisfies v0.2 constraints.
- Add run-state validation, structured cost/risk outcome signals and concurrent-run isolation tests.
- Add active-session tracking, audited Runtime shutdown and explicit delegated child runs.
- Add context-manager failure finalization and cancellation for sessions without an outcome.
- Add a reusable `run_protocol_conformance()` report and framework-neutral Custom Loop example.
- Extend adapter declarations with protocol version, explicit-run, selection, feedback, delegation
  and async capability flags with fail-closed dependency validation.
- Extend conformance reports with required capabilities and explicit `UNSUPPORTED`/`INCONCLUSIVE`
  results instead of treating missing integration signals as success.
- Add asyncio task-isolation coverage and a bounded Codex-like Observe/Act/Verify/Retry example.
- Allow LangGraph bridges to bind directly to a guarded `ExperienceRun` EventSink while rejecting
  cross-run writes and storage-specific adapter options.
- Verify selection, feedback and delegation from persisted protocol-operation evidence in the
  conformance kit rather than trusting capability declarations alone.
- Add `PROTOCOL_API_VERSION = "0.2"` and API snapshot tests for public models and method signatures.
- Add deterministic JSON conformance reports with stable failure, unsupported and inconclusive
  reason codes for CI artifacts and third-party integration diagnostics.
- Add a wheel-installed Protocol smoke covering Custom, LangGraph and Codex-like Loops and wire it
  into the package CI job.
- Add an explicit event compatibility contract: unknown critical event types fail closed, while
  unknown events marked `compatibility=optional` remain integrity-protected and replayable.
- Add a reproducible v0.2 effects benchmark covering protocol latency, safe abstention, automatic
  application prevention, concurrent identity isolation and active-session cleanup.
- Connect v0.2 selection to ACTIVE `PROMPT_DELTA` advice: `task_type` applicability is read from
  the Harness extension policy, explicit token budgets are enforced, and bounded rules are returned
  through `SelectionResult.steps` with `HARNESS_ADOPTION_REQUIRED` audit semantics.

### Compatibility

- Existing `@experience.run`, `@experience.tool`, package mounting and framework adapters remain
  supported and continue to use the same append-only repository.
- v0.2 selection is deterministic, budgeted advice only; it does not execute Policy Delta or control
  a Harness. The Harness must explicitly adopt advice and report it through `feedback()`.

## 0.1.1 - 2026-08-14

### Added

- Add one-line `ExperienceRuntime.mount()` and deferred `experiences=[...]` package mounting.
- Add deterministic Experience Package v2 manifests with package identity, version, requirements,
  content digest and Ed25519 publisher signatures.
- Add repository-local public-key trust stores with key aliases and revocation.
- Add automatic portable capability registration and explainable compatibility bindings.
- Add bounded local/HTTPS package sources, SHA-256 pinning, content-addressed cache and offline mode.
- Add immutable mount reports, package operation events and repository-scoped mutation locks.
- Add local validation, atomic generation upgrade, rollback and audited unmount APIs.
- Add `agent-exp package ...` and `agent-exp trust ...` command groups.

### Security

- External experience always enters quarantine with replay and exact-cache permissions disabled.
- Package integrity or publisher trust never substitutes for caller-controlled local validation.
- Package readers reject extra/duplicate paths, traversal, oversized content and compression bombs.
- Exports strip run-source/evidence identifiers and reject content resembling credentials.
- Signing private keys, generated packages, trust stores, caches and runtime repositories are ignored
  and excluded from distribution artifacts.

### Compatibility

- Existing v0.1.0 repositories remain readable and require no destructive migration.
- Legacy v1 `.exp` packages remain readable as unsigned, quarantined packages.
- `export_package()` / `import_package()` and their CLI commands remain available with deprecation
  guidance; new integrations should use Runtime/package APIs.

## 0.1.0 - 2026-08-14

- Introduce the path-once decorator `ExperienceRuntime` as the primary API.
- Add automatic callable identities, nested/standalone tool contexts and background consolidation.
- Bind LangChain, LangGraph and MCP adapters to the same runtime-owned instrumentation gateway.
- Document generic Skill observation through the same decorator-only application API.
- Add direct weather-tool examples for generic chains and LangChain middleware.
- Prepare the GitHub/PyPI release surface with a new README, logo, API guide and tutorial.
- Remove undeveloped optional extras and stale demo tooling from the published project surface.
- Include measured mining latency consistently in `MiningResult` and experience definitions.
- Normalize text and bytes baseline content before hashing.
- Establish the PyPI project skeleton and architecture decisions.
- Define the initial Protobuf event envelope.
- Add the first framed append-only event log implementation.
- Add Generic Python, LangChain, LangGraph and MCP observation adapters.
- Add verified candidate extraction, parameter variableization and semantic deduplication.
- Add immutable evidence-driven lifecycle revisions and SQLite experience projections.
- Add ACTIVE-only retrieval, safe Advice and controlled registry-only DAG replay.
- Add checksummed `.exp` export and quarantined safe import.
- Add AutoGen/CrewAI capability declarations, CLI commands and PyPI release verification.
- Replace long-text-first experience semantics with baseline-relative `ExperienceDelta` rules.
- Add model-free deterministic mining, rule-level token budgets and baseline deduplication.
- Add measured benefit ledger, break-even activation and automatic benefit quarantine APIs.
- Add domain-neutral feature, baseline and token-estimation extension protocols.
- Add revision-scoped, sample-weighted benefit aggregation and versioned explainable decisions.
