<p align="center">
  <img src="https://raw.githubusercontent.com/LittleRockets/AgentExperience/main/docs/assets/agent-experience-logo.png" alt="AgentExperience" width="520">
</p>

<h1 align="center">AgentExperience</h1>

<p align="center">
  <strong>Give agents memory for what actually worked.</strong><br>
  Capture runtime evidence, validate reusable strategy deltas, and apply only experience that
  earns its token budget.
</p>

<p align="center">
  <a href="https://pypi.org/project/agent-experience/"><img src="https://img.shields.io/pypi/v/agent-experience?color=7c3aed&label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/agent-experience/"><img src="https://img.shields.io/pypi/pyversions/agent-experience" alt="Python versions"></a>
  <a href="https://github.com/LittleRockets/AgentExperience/actions/workflows/ci.yml"><img src="https://github.com/LittleRockets/AgentExperience/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0"></a>
  <a href="https://github.com/LittleRockets/AgentExperience"><img src="https://img.shields.io/badge/status-pre--alpha-f59e0b" alt="Pre-alpha"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/tutorial.md">Tutorial</a> ·
  <a href="docs/api-guide.md">API guide</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

Most agent memory systems store conversations or long summaries. AgentExperience stores a more
conservative object: a **small, baseline-relative strategy delta backed by independent evidence**.
It records how an agent ran, separates success from mere completion, measures the cost and benefit
of reuse, and can quarantine experience that regresses.

```text
runtime events → verified outcomes → candidate delta → validation → benefit gate → active reuse
      │                 │                  │                │               │
  observable         auditable         immutable       token-aware     reversible
```

## Why AgentExperience?

| Capability | What it means |
|---|---|
| Evidence, not anecdotes | A completed run is not automatically a successful run. Deterministic evaluators provide auditable evidence. |
| Minimal experience | The default miner creates structured rules relative to a versioned baseline instead of injecting long model-written summaries. |
| Cost-aware reuse | Rule selection respects context budgets; benefit accounting includes input/output tokens, latency, mining cost and truncation. |
| Safe lifecycle | `CANDIDATE → VALIDATED → ACTIVE`, with quarantine, deprecation and tombstones represented as immutable revisions. |
| Framework neutral | The core has no LangChain, LangGraph, MCP, travel, coding or customer-support semantics. Optional adapters normalize public framework events. |
| Inspectable storage | Checksummed Protobuf events are append-only. SQLite is a rebuildable projection, not the source of truth. |
| Controlled replay | Replay uses registered typed tools, DAG validation, explicit approval and a caller-provided verifier—never arbitrary stored code. |

## Quick start

Install the framework-independent core:

```bash
pip install agent-experience
```

Or add only the integrations you use:

```bash
pip install "agent-experience[langchain,langgraph,mcp]"
```

Create one runtime, specify the storage path once, and decorate the boundaries you want observed:

```python
from agent_experience import agent_experience

experience = agent_experience("./experience-data")

@experience.tool
def get_weather(city: str) -> dict[str, object]:
    return {"city": city, "temperature_c": 22, "fresh": True}

@experience.run(verify=lambda result: bool(result["fresh"]))
def weather_agent(city: str) -> dict[str, object]:
    return get_weather(city)

print(weather_agent("Berlin"))
```

That is the entire integration. AgentExperience automatically owns storage, generates stable run
and tool identities, propagates causation, sanitizes values, records timing and failures, and queues
verified runs for candidate consolidation. There is no Repository, registry, name, contract ID,
producer, rule path or CandidateService to configure.

If you only need observation, omit the verifier:

```python
@experience.run
def agent(task: str):
    return do_work(task)
```

The run is stored, but it cannot create an activatable experience without quality evidence. A
standalone `@experience.tool` call also receives an automatic run context. Call
`experience.flush()` only when a test or short-lived process must wait for background consolidation;
normal applications are flushed when the runtime closes.

### Observe an application Skill

A Skill is simply a reusable callable capability. Decorate its public entry point exactly like a
Tool; the callable's module, signature and code fingerprint become its automatic identity and
version. No Skill name, storage path or experience key is required.

```python
from agent_experience import agent_experience

experience = agent_experience("./experience-data")

@experience.tool
def report_skill(rows: list[dict[str, object]]) -> dict[str, object]:
    report = build_report(rows)  # your existing Skill implementation
    return {"report": report, "passed_checks": validate_report(report)}

@experience.run(verify=lambda result: bool(result["passed_checks"]))
def analyst_agent(rows: list[dict[str, object]]) -> dict[str, object]:
    return report_skill(rows)
```

AgentExperience observes the Skill boundary, sanitized inputs and outputs, latency, failures and
task-level quality evidence. It does not store or execute the Skill's source code, and it does not
mistake a successful function return for a correct result.

Framework integrations reuse the same runtime and storage:

```python
# LangChain: pass this once when constructing the agent.
agent = create_agent(model, tools, middleware=[experience.langchain()])

# LangGraph: feed typed stream events into the runtime-owned bridge.
graph_events = experience.langgraph()

# MCP: wrap an existing ClientSession; no second path or repository.
session = experience.mcp(session, trust_domain="company-internal")
```

## What is observed?

| Source | Observed signals | Not assumed |
|---|---|---|
| Generic Python | run start/completion/failure, sanitized inputs/results, outcome evidence | that a returned result is correct |
| Tools | contract identity, arguments, result/failure, latency, causation | permission to replay the call |
| LangChain 1.x | agent, model and tool lifecycle hooks | graph routing or outcome quality |
| LangGraph 1.x | nodes/tasks, routes, checkpoints, interrupts and resumes | that graph completion means success |
| MCP 1.x | server identity, capabilities, tool calls, resource/prompt identities and hashes | trust in remote content or automatic execution |

Applications decide what constitutes success through deterministic evaluators or custom adapters.
The core provides extension protocols for `FeatureExtractor`, `BaselineResolver`, and
`TokenEstimator`; it does not contain domain keyword tables or benchmark-specific thresholds.

## Experience that must earn its keep

```python
from agent_experience import BreakEvenPolicy

policy = BreakEvenPolicy(
    minimum_measurements=3,
    minimum_holdout_samples=20,
    maximum_input_token_increase=128,
    policy_id="production-break-even",
    policy_version="1",
)
```

Benefit decisions aggregate measurements for the same immutable revision, weighted by sample
count. Rejection reasons are machine-readable: insufficient evidence, quality or success-rate
regression, negative net benefit, token-budget overflow, or output truncation.

## Integrations

| Integration | Install extra | Current level |
|---|---|---|
| Plain Python | core | run + outcome capture |
| LangChain | `langchain` | agent/model/tool observation |
| LangGraph | `langgraph` | graph task/route/interrupt observation |
| MCP Python SDK | `mcp` | capability and client operation observation |
| AutoGen | no extra | capability detection only; host event wiring required |
| CrewAI | no extra | capability detection only; host event wiring required |

See the [tutorial](docs/tutorial.md) for setup and lifecycle examples and the
[API guide](docs/api-guide.md) for the supported public surface.

### Transparent DeepSeek experiment

The paid [end-to-end demo](examples/deepseek_experience_demo.py) prints every model call, selected
rule, token/latency measurement, score, benefit decision and lifecycle transition. It uses travel
only as an application-level benchmark; no travel logic exists in the core package.

```powershell
Copy-Item examples\deepseek_demo_local.example.py examples\deepseek_demo_local.py
# Edit only the ignored deepseek_demo_local.py, then run:
python examples\deepseek_experience_demo.py
```

The demo performs seven model calls. Generated repositories and reports are ignored by Git.

## CLI

```bash
agent-exp verify ./experience-repo
agent-exp inspect ./experience-repo
agent-exp extract ./experience-repo --minimum-confidence 0.8
agent-exp candidates ./experience-repo
agent-exp benefits ./experience-repo
agent-exp export ./experience-repo shared.exp
agent-exp import ./other-repo shared.exp
```

Imported experiences are quarantined until locally reviewed. `.exp` files are data packages, not
trusted executable programs.

## Security model

- inputs and outputs are sanitized before observation;
- raw secrets should never be stored as experience;
- retrieved advice is an untrusted reference and cannot override system or permission policy;
- replay is disabled unless the revision, tool registry, approval policy and verifier all allow it;
- remote MCP resources and prompts are represented by identity/hash where possible;
- imported experience starts in `QUARANTINED`.

Please report vulnerabilities according to [SECURITY.md](SECURITY.md), not in a public issue.

## Project status

AgentExperience is **pre-alpha**. Public APIs and persistent schemas may change before 1.0. The
built-in backend is local, single-process and single-writer; it is not presented as a distributed
event log or multi-tenant service. Review the [API guide](docs/api-guide.md),
[security policy](SECURITY.md) and changelog before production adoption.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LittleRockets/AgentExperience&type=Date)](https://www.star-history.com/#LittleRockets/AgentExperience&Date)

## Development

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"  # Windows
python -m ruff check src tests examples setup.py
python -m mypy src
python -m pytest -q
python -m build
python -m twine check dist/*
```

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) first.

## License

Apache License 2.0. See [LICENSE](LICENSE).
