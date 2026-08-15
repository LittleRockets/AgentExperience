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
  <a href="https://deepwiki.com/LittleRockets/AgentExperience"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
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
and the same request in both calls. The right-hand call received seven generic output constraints
mined deterministically from three successful travel runs; it did not receive a saved New York
answer. The complete content of both responses is shown below. The candidate was injected for
measurement and remained quarantined rather than being silently activated.

| Baseline | Baseline + AgentExperience |
|---|---|
| **Experience input**<br><br>None. The model received only the system prompt and task. | **Experience input**<br><br>`accommodation`, `budget`, `day_completeness`, `dynamic_warning`, `food`, `route_coherence` and `transport` were required. |
| **Opening notes**<br><br>Prices, schedules, opening hours and visa policies are examples or estimates and must be checked through official sources for the actual travel dates.<br><br>The budget is an economy estimate for one person and excludes international flights and shopping.<br><br>Chinese passport holders generally need a B1/B2 visa. Prepare at least two months ahead and follow the latest requirements from the US diplomatic missions in China. | **Pre-trip notes**<br><br>Chinese passport holders need a valid US B1/B2 visa, and EVUS enrollment is generally required. Confirm visa rules and EVUS status with the US diplomatic missions and CBP.<br><br>All attraction hours, ticket prices, subway fares, restaurant hours and prices are references and must be checked through official sources.<br><br>The budget uses USD 1 ≈ CNY 7.2 and excludes international flights, hotels, shopping and unlisted items. |
| **Accommodation**<br><br>First choice: Midtown Manhattan, around Times Square or Koreatown, for convenient transport on a short trip.<br><br>Economy references: Pod 51 and The Jane. If prices are high, consider Long Island City, one subway stop from Manhattan. | **Accommodation**<br><br>Recommended: Midtown Manhattan. Most two-day attractions are in Midtown or Lower Manhattan, subway coverage is dense and several landmarks are walkable.<br><br>Economy/chain hotels: USD 150–250 per night. Mid-range: USD 250–400 per night. Allow CNY 1,500–3,500 per person for two nights; sharing a room lowers the cost.<br><br>Alternatives: Long Island City, about 15 minutes from Midtown by subway, or the Financial District for a Statue of Liberty and Wall Street-focused trip. |
| **Transport overview**<br><br>The subway is the first choice. A single ride is about USD 2.90. A seven-day unlimited pass is mentioned as USD 33, although pay-per-ride is more suitable for two days.<br><br>Expect substantial walking and wear comfortable shoes. | **Transport overview**<br><br>JFK: AirTrain + subway, about 60–75 minutes and USD 11.40; taxi, about USD 70–90 plus tolls and tip. EWR: NJ Transit + subway, about 45–60 minutes and USD 15–18. Verify fares and operating hours.<br><br>City travel: mainly subway. A single ride is listed as USD 2.90; the response suggests a USD 34 seven-day MetroCard or OMNY, with free rides after 12 paid trips in the same week. Pay per ride if taking fewer than 12 trips.<br><br>Combine subway and walking because the itinerary spans Midtown and Lower Manhattan. |
| **Day 1 — Midtown + Lower Manhattan**<br><br>**Morning**<br>08:00 — Leave the hotel; walk or take the subway to Times Square for quieter photos.<br>08:40 — Walk to Bryant Park and the New York Public Library exterior.<br>09:20 — Walk south on Fifth Avenue past the Empire State Building; reserve a timed ticket if going up.<br>10:00 — See Grand Central Terminal's main hall and celestial ceiling.<br>10:40 — Walk or take the subway to the United Nations exterior; confirm tour dates and times if entering.<br><br>**Lunch**<br>Grand Central's lower dining concourse or a nearby quick meal, USD 15–25 per person.<br><br>**Afternoon**<br>13:00 — Take the subway to the Financial District.<br>13:40 — Wall Street, the New York Stock Exchange exterior and Federal Hall.<br>14:20 — Walk to the Charging Bull.<br>14:40 — Continue to Battery Park for a distant Statue of Liberty view.<br>15:20 — Visit the 9/11 Memorial; the museum needs a separate ticket and reservation.<br>16:30 — Walk to the Oculus and see its interior and exterior.<br>17:00 — Walk across Brooklyn Bridge, about 30–40 minutes, with good light before sunset.<br><br>**Dinner and evening**<br>Dinner in DUMBO or Manhattan Chinatown, USD 20–35 per person. Optionally return to Times Square at night or visit Top of the Rock; buy ahead and confirm opening hours.<br><br>**Day 1 budget**<br>Accommodation CNY 800–1,200; food CNY 250–400; subway/bus CNY 50–80; Empire State Building or Top of the Rock CNY 300–450; total CNY 1,400–2,100 excluding shopping. | **Day 1 — Midtown classics + Central Park + Times Square**<br><br>Pace: landmarks in the morning, a relaxed park visit in the afternoon and city lights at night. Expect substantial walking.<br><br>08:00–08:45 — Breakfast at a nearby coffee shop, bagel shop, Ess-a-Bagel or corner deli; CNY 60–100.<br>09:00–10:30 — Enter Central Park from the south and walk to Bethesda Terrace, Bow Bridge and Strawberry Fields; free.<br>10:30–11:00 — Walk or take the subway to Fifth Avenue, passing the Apple flagship and Trump Tower exterior; subway about CNY 21.<br>11:00–12:00 — St. Patrick's Cathedral and Rockefeller Center exterior and sunken plaza; free.<br>12:00–13:00 — Quick lunch near Rockefeller Center; CNY 100–180.<br>13:00–14:30 — Top of the Rock; reserve online. Reference adult price USD 44–50, CNY 320–360, subject to the official site.<br>14:30–15:00 — Walk to the New York Public Library; exterior and lobby are free, subject to opening hours.<br>15:00–15:45 — Bryant Park and the library; rest in the park and visit the library for free.<br>15:45–16:15 — Subway to the Empire State Building; about CNY 21.<br>16:15–17:45 — Empire State Building 86th floor; reference price USD 48–54, CNY 350–390. Choose one observation deck if time is tight.<br>17:45–18:30 — Walk about 15–20 minutes to Koreatown on 32nd Street.<br>18:30–19:30 — Korean dinner, USD 25–40 or CNY 180–290 per person.<br>19:30–21:00 — Walk to Times Square for the lights; watch crowds and personal safety.<br>After 21:00 — Return to the hotel; subway about CNY 21.<br><br>**Day 1 total excluding accommodation:** CNY 1,050–1,400 with both observation decks; choosing one saves about CNY 350. |
| **Day 2 — Central Park + museums + uptown culture**<br><br>**Morning**<br>08:30 — Take the subway to the south side of Central Park.<br>09:00 — Walk through Strawberry Fields, Bow Bridge and Bethesda Fountain.<br>10:30 — Exit on the east side for the Metropolitan Museum of Art. Buy through the official site. New York residents may pay what they wish; non-residents need a ticket. Prioritize the Egyptian galleries, American Wing and European paintings. Hours are usually 10:00–17:00 and may be longer Friday/Saturday; confirm for the date.<br><br>**Lunch**<br>The museum café or a nearby food cart/quick meal, USD 20–30 per person.<br><br>**Afternoon**<br>14:00 — Walk south on Fifth Avenue past the Guggenheim exterior; entry requires another ticket and an opening-hours check.<br>14:40 — Walk around the Jacqueline Kennedy Onassis Reservoir.<br>15:30 — Take the subway to the High Line.<br>16:00 — Walk from the north end to the south end in about 30 minutes, with city and Hudson River views.<br>17:00 — Reach Chelsea Market for snacks or souvenirs.<br>18:00 — Walk to Little Island or Hudson River Park for sunset.<br><br>**Dinner and evening**<br>Dinner in Chelsea or the West Village, USD 25–40 per person. Optionally attend a Broadway show, USD 80–200 with advance purchase, or see the Empire State Building at night.<br><br>**Day 2 budget**<br>Accommodation CNY 800–1,200; food CNY 300–450; subway/bus CNY 50–80; Met ticket CNY 210–280, Broadway excluded; total CNY 1,400–2,000 excluding Broadway. | **Day 2 — Lower Manhattan history + Statue of Liberty + Brooklyn Bridge**<br><br>Pace: ferry in the morning, Lower Manhattan on foot in the afternoon and skyline views from the bridge near sunset. Reserve the Statue of Liberty ferry.<br><br>07:30–08:15 — Breakfast near the hotel; CNY 60–100.<br>08:15–08:45 — Subway from Midtown to Battery Park, about 20–30 minutes; CNY 21.<br>09:00–12:00 — Statue of Liberty + Ellis Island. Buy from the Statue Cruises official site. Reference general ticket USD 25–31; pedestal/crown tickets cost more and require earlier booking. Verify schedules, prices and security requirements; CNY 180–225 for a general ticket.<br>12:00–12:30 — Return to Battery Park and walk about 10 minutes to Wall Street; free.<br>12:30–13:15 — Wall Street, Charging Bull and New York Stock Exchange exterior; expect crowds at the bull; free.<br>13:15–14:00 — Financial District sandwich, salad or food-cart lunch; CNY 90–160.<br>14:00–14:30 — Trinity Church + 9/11 Memorial pools; both free, museum separate.<br>14:30–15:30 — Oculus + 9/11 Memorial exterior. Oculus is free; museum reference price USD 33/CNY 240 and may be skipped if time is tight.<br>15:30–16:00 — Subway to the Manhattan-side Brooklyn Bridge entrance; CNY 21.<br>16:00–17:30 — Walk the 1.8 km bridge in 30–45 minutes; allow 1.5 hours with photos; free.<br>17:30–18:30 — DUMBO + Brooklyn Bridge Park for a Manhattan skyline photo; free.<br>18:30–19:30 — Pizza or American dinner in DUMBO/Brooklyn Heights; USD 25–40 or CNY 180–290.<br>19:30–20:15 — Subway back to the Manhattan hotel, about 20–30 minutes; CNY 21.<br><br>**Day 2 total excluding accommodation:** CNY 570–1,040 with a general Statue of Liberty ticket; add about CNY 240 for the 9/11 Museum. |
| **Complete budget**<br><br>Accommodation CNY 1,600–2,400.<br>Food CNY 550–850.<br>Transport CNY 100–160.<br>Tickets CNY 500–750 for one or two observation decks/museums.<br>**Total: CNY 2,750–4,200 per person.**<br>Increase the budget for Broadway, more observation decks or premium dining. | **Complete budget**<br><br>Food, two breakfasts + two lunches + two dinners: CNY 670–1,120.<br>Tickets: CNY 500–750 for Top of the Rock + Empire State Building + general Statue of Liberty ticket.<br>City transport: CNY 100–150.<br>Airport transfers by public transport: CNY 160–200.<br>**Total excluding international flights and accommodation: CNY 1,430–2,220 per person.**<br>Accommodation separately: CNY 1,500–3,500 per person for two nights; sharing significantly lowers the cost. |
| **Final reminders**<br><br>Use the subway, expect substantial walking and wear comfortable shoes.<br><br>Include one or two indoor activities each day for poor weather.<br><br>Reserve the Statue of Liberty, Empire State Building, Top of the Rock and Met through official sites because same-day inventory or queues may be problematic.<br><br>Opening hours and prices change with seasons and holidays; verify every item before departure. | **Final reminders**<br><br>Buy Statue Cruises tickets for a dated time slot weeks ahead in peak season; crown access needs even earlier booking.<br><br>Reserve Top of the Rock and Empire State Building; poor weather reduces the value of an observation deck.<br><br>Watch belongings in Times Square and subway stations at night; street-costume photos may lead to tip requests.<br><br>Restaurant table service generally expects a 15–20% tip, included in the food estimate.<br><br>Check the forecast and dress for New York's cold winters, humid summers and variable spring/autumn temperatures.<br><br>All prices, schedules and opening hours are references; check official sources for the actual dates. |
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
