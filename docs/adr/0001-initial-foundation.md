# ADR 0001: Initial package and storage foundation

- Status: Accepted for the first implementation milestone
- Date: 2026-08-13

## Decisions

1. The project is an Apache-2.0 licensed PyPI library with distribution name
   `agent-experience` and import name `agent_experience`.
2. Python 3.10 through 3.13 are the initial support target.
3. `pyproject.toml` is the metadata source of truth; `setup.py` is a minimal compatibility shim.
4. The core install depends only on Protobuf. Framework adapters and vector backends are extras.
5. Generated Protobuf Python modules ship in wheels. End-user installation never invokes protoc.
6. The event log is the source of truth. Indexes and vector/graph stores are projections.
7. The MVP is single repository, single writer, multiple readers, and advice-only.
8. Durability supports best-effort, run-durable, and strict-durable policies.
9. A record frame has a fixed header, bounded payload, CRC32 checksum, and monotonically
   increasing sequence number.

## Deferred

- Final public repository URLs and maintainers.
- PyPI ownership confirmation.
- Automated replay and exact cache.
- Multi-process and distributed writers.
- Selection of the default vector backend.

