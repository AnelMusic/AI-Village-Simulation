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


def test_renderer_zoom_pan_tabs_and_overlays(app_config) -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    engine = SimulationEngine(app_config)
    renderer = PygameRenderer(engine, width=900, height=600)
    try:
        zoom_before = renderer.zoom
        renderer._handle_scroll((100, 100), 4)  # wheel over map zooms in
        assert renderer.zoom > zoom_before
        renderer._handle_scroll((100, 100), 5)
        assert abs(renderer.zoom - zoom_before) < 0.2

        cam_before = list(renderer.camera)
        renderer.camera[0] -= 500
        renderer._clamp_camera()
        assert renderer.camera != cam_before or renderer.camera[0] == 500

        # Tab switching cycles villager -> memories -> relationships.
        assert renderer.inspector_tab == "villager"
        renderer._handle_key(_key_t())
        assert renderer.inspector_tab == "memories"
        renderer._handle_key(_key_t())
        assert renderer.inspector_tab == "relationships"
        renderer._handle_key(_key_t())
        assert renderer.inspector_tab == "villager"

        # Overlays render without crashing.
        renderer.show_relationships = True
        renderer.show_heatmap = True
        renderer.selected_agent = next(iter(engine.world.agents))
        renderer.render_frame()

        # Speed keys change the multiplier.
        renderer._handle_key(_key_3())
        assert renderer.speed_index == 2
        renderer._handle_key(_key_1())
        assert renderer.speed_index == 0
    finally:
        renderer.shutdown()
        engine.shutdown()


def _key(name: str) -> int:
    import pygame

    return getattr(pygame, name)


def _key_t() -> int:
    return _key("K_t")


def _key_1() -> int:
    return _key("K_1")


def _key_3() -> int:
    return _key("K_3")


def test_engine_tracks_activity_heatmap(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        x, y = mira.position
        before = engine.world.activity_heatmap[y][x]
        engine.tick()
        engine.wait_for_idle()
        assert engine.world.activity_heatmap[y][x] >= before + 1
    finally:
        engine.shutdown()


def test_heatmap_survives_save_load(app_config, tmp_path) -> None:
    from sim.world import WorldState

    engine = SimulationEngine(app_config)
    try:
        engine.tick()
        engine.wait_for_idle()
        save_path = tmp_path / "world_state.json"
        engine.world.save(save_path)
        loaded = WorldState.load(save_path)
        assert loaded.activity_heatmap
        assert sum(sum(row) for row in loaded.activity_heatmap) >= len(loaded.agents)
    finally:
        engine.shutdown()
