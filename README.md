<p align="center">
  <img src="https://raw.githubusercontent.com/LittleRockets/AgentExperience/main/AgentExperience_logo.png" alt="AgentExperience" width="520">
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
  <a href="https://pypistats.org/packages/agent-experience"><img src="https://img.shields.io/pypi/dm/agent-experience?color=06b6d4&label=downloads" alt="PyPI downloads"></a>
  <a href="https://github.com/LittleRockets/AgentExperience/actions/workflows/ci.yml"><img src="https://github.com/LittleRockets/AgentExperience/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://deepwiki.com/LittleRockets/AgentExperience"><img src="https://deepwiki.com/
  badge.svg" alt="Ask DeepWiki"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0"></a>
  <a href="https://github.com/LittleRockets/AgentExperience/stargazers"><img src="https://img.shields.io/github/stars/LittleRockets/AgentExperience?style=flat&color=fbbf24" alt="GitHub stars"></a>
  <a href="https://github.com/LittleRockets/AgentExperience"><img src="https://img.shields.io/badge/status-pre--alpha-f59e0b" alt="Pre-alpha"></a>
</p>


<p align="center">
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-portable-experience-packages">Packages</a> ·
  <a href="#-transparent-deepseek-experiment">Experiment</a> ·
  <a href="docs/tutorial.md">Tutorial</a> ·
  <a href="docs/api-guide.md">API guide</a> ·
  <a href="#-security-model">Security</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  🧠 Evidence-first &nbsp;·&nbsp; 🧩 Framework-neutral &nbsp;·&nbsp;
  🔐 Safe by default &nbsp;·&nbsp; 📦 Portable
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

## ✨ Why AgentExperience?

| Capability | What it means |
|---|---|
| 🧪 Evidence, not anecdotes | A completed run is not automatically a successful run. Deterministic evaluators provide auditable evidence. |
| 🎯 Minimal experience | The default miner creates structured rules relative to a versioned baseline instead of injecting long model-written summaries. |
| ⚖️ Cost-aware reuse | Rule selection respects context budgets; benefit accounting includes input/output tokens, latency, mining cost and truncation. |
| 🛡️ Safe lifecycle | `CANDIDATE → VALIDATED → ACTIVE`, with quarantine, deprecation and tombstones represented as immutable revisions. |
| 🧩 Framework neutral | The core has no LangChain, LangGraph, MCP, travel, coding or customer-support semantics. Optional adapters normalize public framework events. |
| 🔎 Inspectable storage | Checksummed Protobuf events are append-only. SQLite is a rebuildable projection, not the source of truth. |
| 🔁 Controlled replay | Replay uses registered typed tools, DAG validation, explicit approval and a caller-provided verifier—never arbitrary stored code. |

## 🚀 Quick start

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

### 🛠️ Observe an application Skill

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

## 📦 Portable experience packages

Share validated experience as a data-only `.exp` package, then mount it with one line:

```python
report = experience.mount("./team-patterns.exp")
print(report)
```

Or declare packages once when creating the Runtime; mounting is deferred until decorated Tools and
Skills have registered their capabilities:

```python
experience = agent_experience(
    "./experience-data",
    experiences=["./team-patterns.exp"],
)
```

The Runtime verifies checksums and optional Ed25519 signatures, checks Python/framework/capability
compatibility, creates explainable automatic bindings, deduplicates content and returns a complete
`MountReport`. Imported experience always starts in quarantine. A checksum, trusted publisher or
successful function return can never activate external experience by itself.

Export only validated or active experience:

```python
from agent_experience import PackageSigner

signer = PackageSigner.load("publisher.private-key")
experience.export(
    "team-patterns.exp",
    name="team-patterns",
    version="1.0.0",
    publisher="my-team",
    signer=signer,
)
```

For a locally trusted publisher, add its Ed25519 public key once through `experience.trust` or the
CLI. Signature trust proves package origin; caller-controlled local validation still proves whether
the experience works in the receiving environment.

## 👁️ What is observed?

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

## ⚖️ Experience that must earn its keep

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

## 🧩 Integrations

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

## 🔬 Transparent DeepSeek experiment

The paid [end-to-end demo](examples/deepseek_experience_demo.py) prints every model call, selected
rule, token/latency measurement, score, benefit decision and lifecycle transition. It uses travel
only as an application-level benchmark; no travel logic exists in the core package.

```powershell
Copy-Item examples\deepseek_demo_local.example.py examples\deepseek_demo_local.py
# Edit only the ignored deepseek_demo_local.py, then run:
python examples\deepseek_experience_demo.py
```

The demo performs seven model calls. Generated repositories and reports are ignored by Git.

### Real output comparison: a two-day New York itinerary

This is a real controlled A/B run made on **2026-08-14** with `deepseek-v4-pro`, temperature `0.2`
and the same request in both calls. The model was asked to answer in Chinese; the excerpts below
are faithful English translations of the actual responses. The right-hand call received seven
generic output constraints mined deterministically from three successful travel runs; it did not
receive a saved New York answer. The candidate was injected for measurement and remained
quarantined rather than being silently activated.

| Baseline | Baseline + AgentExperience |
|---|---|
| **Experience input**<br><br>None. The model received only the system prompt and task. | **Experience input**<br><br>`accommodation`, `budget`, `day_completeness`, `dynamic_warning`, `food`, `route_coherence` and `transport` were required. |
| **Day 1 output — translated excerpt**<br><br>“Day 1: Midtown Manhattan + Lower Manhattan classics”<br><br>“08:00 — Leave the hotel and walk or take the subway to Times Square…”<br><br>“13:00 — Take the subway to the Financial District.”<br><br>“17:00 — Walk across Brooklyn Bridge (about 30–40 minutes; the light is best before sunset).” | **Day 1 output — translated excerpt**<br><br>“Day 1: Midtown classics + Central Park + Times Square”<br><br>“Pace: landmark visits in the morning, a relaxed afternoon in the park, and city lights at night.”<br><br>“09:00–10:30 — Central Park… free”<br><br>“13:00–14:30 — Top of the Rock… reference price: about USD 44–50 per adult” |
| **Day 2 output — translated excerpt**<br><br>“Day 2: Central Park + museums + uptown culture”<br><br>“10:30 — Exit the park on the east side and arrive at the Metropolitan Museum of Art.”<br><br>“15:30 — Take the subway to the High Line.”<br><br>“18:00 — Walk to Little Island or Hudson River Park for sunset.” | **Day 2 output — translated excerpt**<br><br>“Day 2: Lower Manhattan history + Statue of Liberty + Brooklyn Bridge”<br><br>“Pace: take the ferry in the morning, connect Lower Manhattan sights on foot in the afternoon, and see the Manhattan skyline from the bridge near sunset.”<br><br>“09:00–12:00 — Statue of Liberty + Ellis Island… verify schedules, prices and security requirements on the official site”<br><br>“16:00–17:30 — Walk across Brooklyn Bridge… allow 1.5 hours including photo stops.” |
| **Budget output — translated**<br><br>“Total: approximately CNY 2,750–4,200.”<br><br>The answer supplies per-day accommodation, food, transit and ticket ranges. | **Budget output — translated**<br><br>“Total: approximately CNY 1,430–2,220 per person,” excluding accommodation, followed by “Budget CNY 1,500–3,500 per person for two nights.”<br><br>The answer also supplies a four-column time/activity/transport/cost schedule for each day. |
| **Verification output — translated**<br><br>“Opening hours and prices change with seasons and holidays; verify every item before departure.” | **Verification output — translated**<br><br>“All prices, schedules and opening hours in this plan are references; check the official sources for your travel dates.” |
| **Measured output**<br><br>2,274 characters<br>84 prompt tokens<br>1,394 completion tokens<br>1,478 total tokens<br>30.867 seconds<br>finish reason: `stop` | **Measured output**<br><br>3,619 characters<br>166 prompt tokens<br>2,259 completion tokens<br>2,425 total tokens<br>45.213 seconds<br>finish reason: `stop` |
| **Deterministic contract score**<br><br>100/100: 2/2 days, transport, accommodation, budget, food, verification warning and route coherence were all detected. | **Deterministic contract score**<br><br>100/100: the same seven requirements were all detected. The scorer reached its ceiling, so it cannot claim a numerical quality lift. |
| **Observed result**<br><br>Already complete and usable, but mostly paragraph-based and less explicit about the cost of each scheduled decision. | **Observed result**<br><br>More granular and easier to audit: explicit daily rhythm, time slots, transfer notes and per-item costs. It also scheduled both Top of the Rock and the Empire State Building on day 1, showing that more detail is not automatically better. |

The primary outcome is answer quality, not minimum token usage. Extra tokens are worthwhile when
they buy useful completeness, feasibility or clarity; token and latency deltas remain cost signals.
This run demonstrates richer structure, but not an automatic quality win. AgentExperience retains
the measurements and quarantines experience that does not clear the configured benefit policy.

## ⌨️ CLI

```bash
agent-exp verify ./experience-repo
agent-exp inspect ./experience-repo
agent-exp extract ./experience-repo --minimum-confidence 0.8
agent-exp candidates ./experience-repo
agent-exp benefits ./experience-repo
agent-exp export ./experience-repo shared.exp
agent-exp import ./other-repo shared.exp
agent-exp package inspect ./experience-repo shared.exp
agent-exp package mount ./experience-repo shared.exp
agent-exp package list ./experience-repo
agent-exp package unmount ./experience-repo team-patterns
agent-exp trust add ./experience-repo publisher-public.pem
```

The original `export/import` commands remain temporarily available for legacy v1 packages. New code
should use the `package` commands. `.exp` files are data packages, not trusted executable programs.

## 🔐 Security model

- inputs and outputs are sanitized before observation;
- raw secrets should never be stored as experience;
- retrieved advice is an untrusted reference and cannot override system or permission policy;
- replay is disabled unless the revision, tool registry, approval policy and verifier all allow it;
- remote MCP resources and prompts are represented by identity/hash where possible;
- imported experience starts in `QUARANTINED`.

Please report vulnerabilities according to [SECURITY.md](SECURITY.md), not in a public issue.

## 🧭 Project status

AgentExperience is **pre-alpha**. Public APIs and persistent schemas may change before 1.0. The
built-in backend is local, single-process and single-writer; it is not presented as a distributed
event log or multi-tenant service. Review the [API guide](docs/api-guide.md),
[security policy](SECURITY.md) and changelog before production adoption.

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LittleRockets/AgentExperience&type=Date)](https://www.star-history.com/#LittleRockets/AgentExperience&Date)

## 🧰 Development

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

## 📄 License

Apache License 2.0. See [LICENSE](LICENSE).
