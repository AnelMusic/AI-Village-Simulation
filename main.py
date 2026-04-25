from __future__ import annotations

import argparse
import time

from sim import SimulationEngine, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Village Sim")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--headless", action="store_true", help="Run without Pygame")
    parser.add_argument("--new-world", action="store_true", help="Ignore any existing save file")
    parser.add_argument("--duration-seconds", type=float, default=None, help="Optional wall-clock runtime limit")
    return parser


def run_headless(engine: SimulationEngine, duration_seconds: float | None) -> None:
    start = time.monotonic()
    last = start
    while True:
        now = time.monotonic()
        dt = now - last
        last = now
        engine.update(dt if dt > 0 else 0.05)
        time.sleep(0.05)
        if duration_seconds is not None and now - start >= duration_seconds:
            break


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    engine = SimulationEngine.load_or_create(config, new_world=args.new_world)
    try:
        if args.headless:
            run_headless(engine, args.duration_seconds)
        else:
            from renderer import PygameRenderer

            renderer = PygameRenderer(engine)
            try:
                renderer.run()
            finally:
                renderer.shutdown()
    finally:
        engine.shutdown()
        print(
            "Token usage:"
            f" input={engine.cost_tracker.input_tokens}"
            f" output={engine.cost_tracker.output_tokens}"
            f" estimated_cost=${engine.cost_tracker.estimated_cost:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
