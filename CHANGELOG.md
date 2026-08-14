# Changelog

All notable changes will be documented in this file.

## Unreleased

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
