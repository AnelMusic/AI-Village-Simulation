# Village Sim

Village Sim is a 2D tile-based social sandbox where a small group of AI villagers share one world, one set of resources, and a growing web of memories, favors, routines, and infrastructure.

Each villager acts independently through structured tool calls. They can move, rest, sleep, cook, fish, forage, gather flowers, trade, give gifts, contribute to public projects, propose alliances, and broadcast to nearby groups. The goal is not a scripted story, but emergent village behavior you can watch, tune, and study.

<img width="1176" height="754" alt="image" src="https://github.com/user-attachments/assets/44560c65-ac6b-4ebf-8004-3aa6c571765b" />


## Project Goal

The intent of the project is to explore questions like:

- What kinds of social dynamics emerge when agents have persistent memory and different personalities?
- How do shared pressures like food, warmth, and morale shape cooperation?
- Can subtle incentives produce believable collaboration without hard-scripting every behavior?
- How does changing prompts or map structure reshape the culture of the village?

This is meant to be part simulation, part sandbox, and part experiment.

## Sample Simulation Summary

####  Community Projects
- The villagers spent most of their time contributing materials to three key projects:

- Wood Shed: the most-contributed project; provides village-wide warmth and better rest recovery
- Granary: food security backup; Mira and Asha pushed wheat and wood into it early
- Bathhouse: the late-game priority flagged on the notice board; needed wood + wheat to make the village center more "livable" and improve recovery

#### Resource Gathering

- Bolt was the main woodcutter, chopping from nearby forest tiles throughout
- Asha farmed wheat from communal plots repeatedly
- Mira and Fen cooked fish into meals at the community hearth for better food value

####  Social/Market Activity

- Market hours triggered movement toward the plaza, with Fen and Luma most active in seeking trades and social leverage
- Fen gave Mira a flower gift as a relationship/influence move
- Several villagers tried to position themselves as "the person people remember" for keeping the village warm

## Current Feature Set

- Shared tile world with:
  - houses
  - plaza
  - well
  - community hearth
  - notice board
  - communal farm
  - forests
  - berry grove
  - pond
  - flower garden
  - visible public project sites
- AI villagers with:
  - configurable personalities
  - per-agent memory
  - relationship tracking
  - trust, favors, gifts, and alliances
  - persistent save/load state
- Resource and village systems:
  - food
  - warmth
  - morale
  - wood
  - wheat
  - berries
  - fish
  - flowers
  - meals
- Social actions:
  - direct speech
  - local group announcements
  - trade offers and responses
  - gifting
  - alliance proposals and responses
  - house visits
- Village progression:
  - granary
  - wood shed
  - market stalls
  - bathhouse
  - greenhouse
- Comfort systems:
  - well-based resting
  - house fires that improve nighttime recovery
  - subtle cooperation bonuses when agents work near each other
  - extra hidden benefits for allied villagers
- Two run modes:
  - Pygame viewer
  - headless simulation runner

## Installation

### Requirements

- Python 3.11+
- An OpenAI API key if you want live LLM-driven villagers

### Install dependencies

```bash
pip install -r requirements.txt
```

### Optional API key

Preferred:

```powershell
$env:OPENAI_API_KEY="sk-..."
```

You can also place the key in `config.yaml`, but using an environment variable is strongly recommended.

If no key is present, the simulation still runs with a deterministic fallback policy.

## How To Run

### Normal Pygame mode

```bash
python main.py
```

### Start with a fresh world

```bash
python main.py --new-world
```

### Headless mode

```bash
python main.py --headless
```

### Headless mode for a limited duration

```bash
python main.py --headless --duration-seconds 30
```

### Use a custom config file

```bash
python main.py --config my_config.yaml
```

## Command Reference

Main commands:

```bash
python main.py
python main.py --new-world
python main.py --headless
python main.py --headless --duration-seconds 30
python main.py --config my_config.yaml
pytest
```

What they do:

- `python main.py`
  - launches the Pygame simulation viewer
- `python main.py --new-world`
  - discards the current save and generates a fresh world
- `python main.py --headless`
  - runs the simulation without the renderer
- `python main.py --headless --duration-seconds 30`
  - runs headless for a fixed wall-clock duration
- `python main.py --config my_config.yaml`
  - runs with a custom config file
- `pytest`
  - runs the test suite

## Controls

In the Pygame viewer:

- Click a villager to inspect them
- Use the mouse wheel over the inspector to scroll
- Resize the window freely

The inspector shows:

- current action
- energy
- inventory
- latest thought
- relationship summaries
- village state
- project progress

## Configuration

Most of the simulation is driven by `config.yaml`.

You can change:

- model
- tick rate
- world size
- autosave interval
- concurrent model call cap
- character names
- colors
- house positions
- personalities
- starting inventory overrides

Important note:

- The world generator currently gives every villager a generous baseline inventory boost at world creation so the simulation has more room to branch early.

## Data And Persistence

The simulator writes local state into:

- `data/world_state.json`
- `data/memory/`
- `data/relationships.json`
- `logs/events.csv`

On startup, the sim resumes from the existing save unless you pass `--new-world`.

## Architecture

The project is split into a simulation core and a renderer.

### High-level flow

1. `main.py` loads config and creates the simulation engine
2. `SimulationEngine` owns world time, autosave, scheduling, logging, and decision execution
3. each villager gets an observation built from world state, memory, relationships, and current opportunities
4. a decision policy chooses one structured action
5. the action resolver validates and applies the result
6. the renderer reads the same world state and visualizes it live

### Important modules

- `main.py`
  - CLI entrypoint
  - chooses GUI or headless mode
- `sim/config.py`
  - pydantic config models
  - default characters and settings
- `sim/world.py`
  - world dataclasses
  - map generation
  - save/load state
- `sim/engine.py`
  - main simulation loop
  - scheduling
  - movement
  - energy updates
  - autosave
  - rate/cost tracking
- `sim/actions.py`
  - action validation and world mutation
  - project contributions
  - trades
  - gifts
  - alliances
  - cooking, gathering, resting, sleeping
- `sim/agent.py`
  - observation builder
  - system prompt construction
  - OpenAI-backed decision policy
  - heuristic fallback policy
- `sim/relationships.py`
  - trust
  - trade count
  - gifts
  - favors
  - alliances
- `sim/memory.py`
  - local per-agent memory storage
- `sim/tools.py`
  - action/tool schemas exposed to the model
- `renderer/game.py`
  - Pygame UI
  - map drawing
  - house and agent visuals
  - inspector sidebar

### Design approach

Some project choices are intentional:

- world mutation is centralized
  - the engine and action resolver are the main places where state should change
- agents do not get free-form powers
  - they must act through the tool schema
- the renderer is a reader, not the source of truth
  - gameplay state should live in `sim/`, not in `renderer/`
- saves are local and inspectable
  - JSON files and CSV logs are part of the workflow
- fallback behavior matters
  - the heuristic policy exists so the sim is still testable and runnable without an API key

## Contributing Guide

If you want to contribute, this is the easiest mental map:

### If you want to change behavior

- change prompts or observation framing in `sim/agent.py`
- change action effects and validation in `sim/actions.py`
- change simulation timing, rerouting, energy, or scheduling in `sim/engine.py`
- change map layout and world generation in `sim/world.py`

### If you want to add a new mechanic

Usually the path is:

1. add world state if needed in `sim/world.py`
2. add tool schema in `sim/tools.py`
3. implement the action in `sim/actions.py`
4. expose it in observations or heuristics in `sim/agent.py`
5. visualize it in `renderer/game.py` if it should be visible
6. add tests under `tests/`

### If you want to tune emergent behavior

The main leverage points are:

- character personalities in `config.yaml` and `sim/config.py`
- observation text in `sim/agent.py`
- hidden incentives in `sim/actions.py`
- routing and anti-loop logic in `sim/engine.py`
- map structure in `sim/world.py`

### If you want to debug a weird run

Start here:

- `logs/events.csv`
- console output
- `data/world_state.json`
- `data/relationships.json`

Then inspect:

- `sim/agent.py` for why the agent thought something
- `sim/engine.py` for reroutes and low-energy corrections
- `sim/actions.py` for whether the action was valid and what it actually did

### Testing expectations

Contributions should ideally include or update tests when they affect:

- action behavior
- save/load format
- world generation
- headless simulation behavior
- renderer stability

## Testing

Run the test suite with:

```bash
pytest
```

## Current Limitations

The project works, but it is still rough in important ways.

- Agents can still fall into repetitive project-contribution loops, especially when one public project looks like the best local payoff.
- Energy behavior is improved, but not yet truly strategic. Agents still sometimes overcommit before recovery.
- The model can still produce reasoning that sounds smarter than the resulting action.
- Invalid target correction helps a lot, but the agents are not yet fully grounded planners.
- Social behavior is better than before, but alliances, gifts, and favors still need more tuning to create rich long-term politics.
- Public projects are meaningful, but agents can over-prioritize them once they identify them as high-value.
- Market hour creates convergence, but trade frequency is still lower than ideal for a village economy sim.
- Headless runs with live models can hit OpenAI rate limits, especially at higher tick rates or with too much repeated reasoning.
- There is currently no exponential backoff/retry system for rate-limit handling, so `429` errors can still appear in logs and temporarily degrade behavior.
- Some emergent behavior is interesting, but the village can still feel too optimization-driven instead of fully alive.

## What Needs Improvement Next

The best next steps would be:

- better anti-loop logic for repeated project contributions
- smarter long-horizon energy planning
- stronger reasons for agents to visit each other intentionally
- more meaningful use of favors and alliance obligations
- better trade economics and scarcity balancing
- event systems that force re-prioritization
- stronger differentiation between home life, work life, and social life
- retry/backoff for API failures and rate limits
- clearer in-world signs that a project or social system has changed behavior

## Why The Logs Matter

The console output and `logs/events.csv` are part of the project, not just debug noise. They make it possible to study:

- coordination failures
- project fixation
- social clustering
- trust formation
- loop behavior
- resource bottlenecks
- prompt changes over time

## Status

This is a working experimental v1, not a finished game.

It is already useful as:

- a prompt-design sandbox
- a social-agent experiment
- a toy artificial society
- a base for further simulation design

It still needs another few passes before the village reliably feels deep, socially rich, and consistently believable over long runs.
