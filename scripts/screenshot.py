"""Run the village briefly and capture a screenshot of the Pygame viewer.

Useful for refreshing README art after viewer or world changes:

    python scripts/screenshot.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pygame

# Make the project root importable when run as `python scripts/screenshot.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from renderer import PygameRenderer
from sim import SimulationEngine, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture a Village Sim viewer screenshot")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--output", default="docs/screenshot.png", help="Where to save the PNG")
    parser.add_argument("--seconds", type=float, default=6.0, help="Wall-clock seconds to let the village run first")
    parser.add_argument("--speed", type=float, default=8.0, help="Simulation speed multiplier while warming up")
    parser.add_argument("--select", default=None, help="Villager to select in the inspector (default: first)")
    parser.add_argument("--new-world", action="store_true", help="Generate a fresh world instead of resuming the save")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    engine = SimulationEngine.load_or_create(config, new_world=args.new_world)
    renderer = PygameRenderer(engine)
    try:
        elapsed = 0.0
        while elapsed < args.seconds:
            dt = renderer.clock.tick(60) / 1000.0
            renderer.process_events()
            engine.update(dt * args.speed)
            renderer.render_frame()
            elapsed += dt
        renderer.selected_agent = args.select or next(iter(engine.world.agents))
        renderer.render_frame()
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(renderer.screen, output)
        print(f"Saved screenshot: {output}")
    finally:
        renderer.shutdown()
        engine.maybe_autosave()
        engine.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
