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

        agent_name = next(iter(engine.world.agents))
        agent = engine.world.agents[agent_name]
        renderer._handle_click(renderer._agent_center(agent))
        assert renderer.selected_agent == agent_name
        renderer.render_frame()

        renderer._inspector_content_height = 2000
        renderer._handle_scroll((renderer.screen.get_width() - 10, 100), 5)
        assert renderer.inspector_scroll > 0

        renderer._handle_click((3, renderer.screen.get_height() - 3))
        assert renderer.selected_agent is None
        renderer.render_frame()
    finally:
        renderer.shutdown()
        engine.shutdown()
