from __future__ import annotations

import os

from renderer import PygameRenderer
from sim.engine import SimulationEngine


def test_pygame_renderer_starts_and_renders(app_config) -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    engine = SimulationEngine(app_config)
    renderer = PygameRenderer(engine, width=640, height=480)
    try:
        renderer.process_events()
        renderer.render_frame()
    finally:
        renderer.shutdown()
        engine.shutdown()
