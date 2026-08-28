# Village Sim

A 2D tile-based social sandbox where a handful of AI villagers share one world, one set of resources, and a slowly thickening web of memories, favors, grudges, promises, and public infrastructure.

Each villager is an autonomous agent that perceives the world through text, decides through structured tool calls, and lives with the consequences: hunger, cold, exhaustion, social debt, trust, and the lasting effects of what they build or fail to build. The goal is not a scripted story — it is emergent village behavior you can watch, tune, and study.

<img width="1176" height="754" alt="Village Sim running in the Pygame viewer" src="https://github.com/user-attachments/assets/44560c65-ac6b-4ebf-8004-3aa6c571765b" />

## Why this exists

The project is part simulation, part sandbox, part prompt-design experiment. Questions it is meant to explore:

- What social dynamics emerge when agents have persistent memory and different personalities?
- How do shared pressures — food, warmth, morale — shape cooperation versus hoarding?
- Can subtle incentives (price hints, share credits, trust, promises) produce believable collaboration without hard-scripting behavior?
- How do prompt or map changes reshape the culture of the village over days and seasons?

## How a villager works

Every villager runs the same loop, tick after tick:

1. **Observe** — a text observation is built from world state, nearby tiles, personal needs, memory, relationships, open promises, pending offers, project opportunities, and village-wide stockpiles (which double as trade price hints).
2. **Decide** — the agent picks exactly one structured action (or submits a multi-step plan) through a tool-call schema. There are no free-form powers.
3. **Act** — the action resolver validates and applies it to the world. Invalid actions fail and waste the turn.
4. **Remember** — salient events are written to per-agent memory and to the shared event log.

Decisions come from one of two policies:

- **LLM policy** — if an `OPENAI_API_KEY` is present, decisions come from the configured model. Live calls are wrapped in a resilience layer: transient errors (rate limits, timeouts, 5xx) retry with exponential backoff and jitter, and a circuit breaker falls back to the heuristic policy during outages so the village keeps living instead of silently stalling.
- **Heuristic policy** — with no key (or during an outage), a deterministic fallback policy runs the village. It pursues food, warmth, and social contact, trades, contributes to projects, breaks out of action loops, and goes home to sleep when exhausted. This keeps the sim fully runnable and testable offline.

Engine guardrails correct pathological decisions (invalid targets, actions attempted while exhausted, repetitive loops). Every override is logged as an `engine_override` event, so guardrail behavior is auditable rather than hidden.

## Feature tour

### The world

- 24×24 tile map (configurable): houses, plaza, well, community hearth, notice board, communal farm, forests, berry grove, pond, flower garden, and five public project sites.
- Day/night cycle with sleeping, house fires for better nighttime recovery, and well-side rests.
- Four seasons — spring, summer, autumn, winter — each lasting 4 in-game days. Winter slows regrowth and chills villagers; seasons change what sensible behavior looks like.
- Random world events: storms that chill and drain, festivals that pull everyone to the plaza, shortages that pause regrowth, and traveling traders.

### Needs and survival

- Per-villager hunger, warmth, and loneliness, scaled mechanically by personality traits.
- Energy that drains with work and recovers with rest, sleep, festivals, and comfort; exhaustion forces reroutes toward recovery.
- Village-level pressures — food, warmth, morale (0–12 each) — that sink morale when they run low and are broadcast to every agent through the notice board.

### Economy

- Resources: wood, wheat, berries, fish, flowers, meals. Raw food cooks into meals at the community hearth for better value.
- Market hour opens at the plaza every ~20 seconds (longer once market stalls are built), making plaza trades and conversation more rewarding.
- Village-wide stockpiles are surfaced to agents as scarcity price hints: scarce goods trade high, plentiful goods trade low.
- Full trade flow: offers, accepts, rejections, and counter-offers. Hostile or distrusting villagers refuse gifts and deals.
- Traveling traders offer premium swaps (up to double rate) — but selling food to outsiders tightens village supply.

### Social fabric

- Direct speech to adjacent villagers and announcements to nearby groups; conversations expect replies.
- Persistent relationships with trust (−1..+1), trade counts, gifts, favors, and alliances. Trust decays toward neutral over time.
- Gifts build trust and earn favor; favors can be called in through help requests.
- **Promises**: saying "I'll bring you wood" or "you have my word" creates a remembered promise for both parties. Keeping it builds trust; breaking it stings; letting it lapse cools the relationship. Open promises are surfaced in observations until settled.

### The commons

Five public projects, built from pooled wood and wheat, with visible construction sites and contributor credit:

| Project | Cost (wood / wheat) | What it changes |
| --- | --- | --- |
| Granary | 6 / 10 | Unlocks the shared granary store |
| Wood Shed | 12 / 4 | Steadier warmth, more effective rest |
| Market Stalls | 8 / 6 | Longer market hours, better plaza life |
| Bathhouse | 10 / 5 | Better recovery around the village center |
| Greenhouse | 12 / 8 | Crops and flowers keep thriving across seasons |

The **granary** is the centerpiece hoarding dilemma: deposits of wheat, berries, fish, or meals earn personal, withdrawable share credits — but the shared store also rations food to the village during shortages and storms. Keeping everything private is always allowed; contributing is a genuine choice with real trade-offs.

### Planning

Agents can commit to multi-step plans instead of deciding tick-by-tick. Plans come in three horizons — short (5 steps), a workday (8), or a season (10) — and are interrupted when something important happens: someone speaks to them, an offer arrives, market hour starts, or their energy crashes. Season-length plans pause at each season change so the agent can rethink.

## Quick start

### Requirements

- Python 3.11+
- Windows, macOS, or Linux
- An OpenAI API key *only* if you want live LLM-driven villagers (optional)

### Install

```bash
pip install -r requirements.txt
```

### Optional: API key

Set the key in your environment (recommended):

```powershell
# PowerShell
$env:OPENAI_API_KEY="sk-..."
```

```bash
# bash/zsh
export OPENAI_API_KEY="sk-..."
```

The key can also go in `config.yaml`, but an environment variable is strongly preferred. The shipped config keeps `openai_key: null`, so behavior is driven by the environment, never by a placeholder string.

Without a key, everything still runs on the deterministic heuristic policy — including the full test suite.

### Run it

```bash
python main.py            # Pygame viewer (default)
python main.py --headless # no renderer
```

On exit, the console prints total token usage and estimated cost for the run.

## Command reference

| Command | What it does |
| --- | --- |
| `python main.py` | Launch the Pygame viewer and resume (or create) the world |
| `python main.py --new-world` | Ignore any existing save and generate a fresh world |
| `python main.py --headless` | Run without the renderer |
| `python main.py --headless --duration-seconds 30` | Headless for a fixed wall-clock duration |
| `python main.py --config my_config.yaml` | Use a custom config file |
| `pytest` | Run the test suite |

## The Pygame viewer

### Controls

| Input | Action |
| --- | --- |
| Left click | Select a villager to inspect (click empty map to deselect) |
| Mouse wheel over inspector | Scroll the inspector |
| Mouse wheel over map | Zoom the camera (0.6×–3×) |
| Right-drag / arrow keys | Pan the camera (clamped to the map) |
| `SPACE` | Pause / resume |
| `1` / `2` / `3` | Speed: 1× / 3× / 8× |
| `T` | Cycle inspector tab: villager / memories / relationships |
| `R` | Toggle relationship-graph overlay (trust-colored edges, gold for alliances) |
| `H` | Toggle activity heatmap (where villagers actually spend time) |
| `ESC` | Quit |

The window resizes freely. The map shows speech bubbles, plan labels, energy bars, day/night tint, project sites, and a live feed of recent public events. The inspector shows current action, energy, needs, inventory, latest thought, active plan, project progress with contributor credit, plus memory-timeline and relationships tabs.

## Configuration

Everything runs off `config.yaml`. The most useful knobs:

| Key | Meaning |
| --- | --- |
| `openai_key` | Prefer the `OPENAI_API_KEY` env var; leave `null` to run heuristic-only |
| `model` | Model used for villager decisions (shipped default: `gpt-5.4-nano`) |
| `max_tokens_per_turn` | Response budget per decision |
| `ticks_per_second` | Simulation speed (shipped default: `0.5` = one tick every 2s) |
| `world_size` | Map is `world_size × world_size` tiles |
| `day_length_seconds` | Length of one in-game day |
| `autosave_interval_seconds` | How often world state is written |
| `max_concurrent_model_calls` | Cap on parallel API calls |
| `log_thoughts` | Print villager thoughts to the console |
| `pricing` | Per-million token prices used for the cost estimate |
| `characters` | Per-villager name, color, house, starting inventory, traits, personality |

Traits (`food_focus`, `warmth_focus`, `social_focus`) are multipliers on need accumulation — they mechanically shape behavior, not just flavor. Personalities are free-text prompts; they are the single biggest lever on village culture.

## The default villagers

| Villager | House | Starting goods | In one line |
| --- | --- | --- | --- |
| **Mira** | (4, 4) | 0 wood, 4 wheat | Blunt field steward obsessed with food security and follow-through |
| **Fen** | (19, 4) | 1 wood, 1 wheat | Silver-tongued trader who converts charm and timing into leverage |
| **Asha** | (4, 19) | 0 wood, 3 wheat | Healer-mediator who turns resources into shared comfort |
| **Bolt** | (19, 19) | 4 wood, 0 wheat | Gruff builder who trusts labor, not promises |
| **Luma** | (12, 4) | 0 wood, 2 wheat | Distractible tinkerer running little experiments on village life |

## Data, saves, and observability

The sim writes plain, inspectable files — they are part of the workflow, not debug noise:

| Path | Contents |
| --- | --- |
| `data/world_state.json` | Full world state (grid, agents, projects, offers, granary, promises) |
| `data/memory/<name>_memory.json` | Per-agent memory: 20 recent events + rolling summaries |
| `data/relationships.json` | Trust, trades, favors, gifts, alliances between every pair |
| `logs/events.csv` | Append-only event log: tick, day, time-of-day, kind, actor, target, location, summary, thought |

On startup the sim resumes the existing save unless you pass `--new-world`.

The event log makes it possible to study coordination failures, project fixation, social clustering, trust formation, loop behavior, resource bottlenecks, and the effect of prompt changes over time. `engine_override` rows show exactly where and why the engine stepped in.

## Architecture

The project is split into a simulation core (`sim/`) and a renderer (`renderer/`) that only reads state.

```text
main.py              CLI entrypoint; picks GUI or headless mode
sim/config.py        pydantic config models, default characters, YAML loading
sim/world.py         world dataclasses, map generation, save/load (schema-versioned)
sim/engine.py        tick loop: time, seasons, events, needs, movement, plans,
                     decision scheduling, guardrails, autosave, cost tracking
sim/agent.py         observation builder, system prompts, LLM decision policy,
                     heuristic fallback policy, retry/circuit-breaker wrapper
sim/actions.py       action validation and world mutation: work, trade, gifts,
                     alliances, granary, promises, festival/trader actions
sim/relationships.py trust, favors, gifts, alliances, daily decay
sim/memory.py        per-agent persistent memory
sim/tools.py         the tool schemas exposed to the model
renderer/game.py     Pygame UI: map, inspector, overlays, camera, event feed
tests/               58 tests covering actions, economy, dialogue, engine,
                     fallback, plans, projects, persistence, renderer smoke
```

Design principles, intentionally:

- **World mutation is centralized** — the engine and action resolver are the only places state changes.
- **Agents act only through tools** — no free-form powers; invalid actions fail visibly.
- **The renderer is a reader** — gameplay state lives in `sim/`, never in the UI.
- **Saves are local and inspectable** — JSON and CSV are the observability surface.
- **Fallback behavior is first-class** — the heuristic policy keeps the sim runnable, testable, and cheap.

## Development guide

Run the tests:

```bash
pytest
```

**Change behavior:** prompts and observation framing live in `sim/agent.py`; action effects and validation in `sim/actions.py`; timing, reroutes, and scheduling in `sim/engine.py`; map layout in `sim/world.py`.

**Add a mechanic:**

1. Add world state in `sim/world.py` (and bump the save schema if needed)
2. Add the tool schema in `sim/tools.py`
3. Implement the action in `sim/actions.py`
4. Expose it in observations/heuristics in `sim/agent.py`
5. Visualize it in `renderer/game.py` if it should be visible
6. Add tests under `tests/`

**Tune emergence:** personalities in `config.yaml`, observation text in `sim/agent.py`, hidden incentives in `sim/actions.py`, routing and anti-loop logic in `sim/engine.py`, map structure in `sim/world.py`.

**Debug a weird run:** start with `logs/events.csv`, console output, `data/world_state.json`, and `data/relationships.json`. Then inspect `sim/agent.py` (why it thought that), `sim/engine.py` (reroutes/overrides), and `sim/actions.py` (what the action actually did).

## Current limitations

This is a working experimental v1, not a finished game. Honest gaps:

- Agents can still over-commit to one project when it looks like the best payoff; guardrails reduce but do not eliminate loops.
- Promise settlement is phrase-based: saying "as promised" settles a promise even if the promised item never changed hands.
- Trade has price hints and counter-offers, and the granary adds share credits — but a truly negotiated economy (prices, ownership beyond share credits) is still open.
- The viewer does not yet visualize granary contents, share credits, or open promises.
- Live API runs can hit rate limits at high tick rates; the circuit breaker degrades gracefully to heuristic behavior during outages.

## Roadmap

The best next steps:

- **Action-grounded promises** — fulfilling "I'll bring you wood" by actually giving the wood, not just claiming it happened.
- **Viewer visibility** for granary contents, share credits, and open promises.
- **Deeper dialogue memory** so conversations reference more than promises.
- **Tuning from real long runs** — hoarding dilemma pressure, trader premium rates, and event frequency.

## License

[MIT](LICENSE) © 2026 Anel Music
