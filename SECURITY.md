# Security Policy

AgentExperience handles prompts, tool inputs, outputs, and execution metadata that may contain
sensitive data. Do not include credentials or private production traces in public issues.

Until a private reporting address is established, do not publish exploitable vulnerabilities.
Contact the repository owner privately and include the affected version and reproduction steps.

## Portable experience packages

- `.exp` files are bounded data-only ZIP containers; Python, pickle, bytecode and extra paths are rejected.
- SHA-256 protects integrity. Optional Ed25519 signatures authenticate a publisher key.
- A valid signature is not local quality evidence and never activates imported experience.
- External revisions enter quarantine with replay and exact-cache permissions disabled.
- HTTPS sources enforce size, timeout and redirect limits; digest pinning is recommended.
- Private signing keys, trust stores, package caches and generated `.exp` files must not be committed.
- Export removes run-source identifiers and rejects content resembling credentials or tokens.
- Report malformed packages, unsafe binding or activation bypasses as security issues.
