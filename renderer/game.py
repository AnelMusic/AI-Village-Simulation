from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from sim.engine import SimulationEngine
    from sim.world import AgentState


SIDEBAR_WIDTH = 360
HEADER_HEIGHT = 56
SCROLL_STEP = 28
HUD_COLOR = (24, 26, 32)
SIDEBAR_COLOR = (30, 32, 40)
TEXT_COLOR = (230, 230, 235)
MUTED_COLOR = (160, 162, 172)
ACCENT_COLOR = (240, 200, 90)

TILE_COLORS: dict[str, tuple[int, int, int]] = {
    "grass": (100, 158, 96),
    "road": (172, 164, 142),
    "forest": (48, 104, 62),
    "berry_grove": (148, 70, 118),
    "water": (56, 108, 178),
    "flower_garden": (204, 148, 190),
    "farm": (186, 166, 88),
    "house": (172, 120, 78),
    "well": (108, 110, 132),
    "hearth": (206, 104, 52),
    "notice_board": (142, 102, 62),
}

CROP_OVERLAYS: dict[str, tuple[int, int, int, int]] = {
    "empty": (0, 0, 0, 0),
    "growing": (90, 140, 40, 110),
    "ripe": (240, 210, 60, 150),
}

SITE_LABELS: dict[str, str] = {
    "granary_site": "GRANARY",
    "wood_shed_site": "WOOD SHED",
    "market_site": "MARKET",
    "bathhouse_site": "BATHHOUSE",
    "greenhouse_site": "GREENHOUSE",
    "dock": "DOCK",
    "market_stall_frame": "",
    "hearth_seat": "",
    "berry_bush": "",
    "flower_patch": "",
    "pond": "",
    "hearth_seat_feature": "",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class PygameRenderer:
    """Pygame viewer for the village simulation.

    The renderer is a reader, not the source of truth: it draws whatever the
    engine's world state contains. Controls:
      - click a villager to inspect them (click empty map to deselect)
      - mouse wheel over the inspector scrolls it
      - SPACE pauses/resumes the simulation, ESC quits
      - the window can be resized freely
    """

    def __init__(self, engine: SimulationEngine, width: int = 1180, height: int = 760) -> None:
        pygame.init()
        pygame.display.set_caption("Village Sim")
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.font = pygame.font.Font(None, 20)
        self.small_font = pygame.font.Font(None, 17)
        self.title_font = pygame.font.Font(None, 26)
        self.clock = pygame.time.Clock()
        self.engine = engine
        self.running = True
        self.paused = False
        self.selected_agent: str | None = None
        self.inspector_scroll = 0
        self._inspector_content_height = 0

    # ------------------------------------------------------------------ loop

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self.process_events()
            if not self.paused:
                self.engine.update(dt if dt > 0 else 0.016)
            self.render_frame()
        self.engine.maybe_autosave()

    def shutdown(self) -> None:
        pygame.quit()

    # ---------------------------------------------------------------- events

    def process_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self.paused = not self.paused
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                self._handle_scroll(event.pos, event.button)

    def _handle_click(self, position: tuple[int, int]) -> None:
        if position[0] >= self.screen.get_width() - SIDEBAR_WIDTH:
            return
        hit = self._agent_at(position)
        self.selected_agent = hit.name if hit is not None else None
        self.inspector_scroll = 0

    def _handle_scroll(self, position: tuple[int, int], button: int) -> None:
        if position[0] < self.screen.get_width() - SIDEBAR_WIDTH:
            return
        direction = -1 if button == 4 else 1
        self.inspector_scroll = _clamp(
            self.inspector_scroll + direction * SCROLL_STEP,
            0,
            max(0, self._inspector_content_height - self._inspector_view_height()),
        )

    # ------------------------------------------------------------- geometry

    def _map_area(self) -> tuple[int, int, int, int]:
        width, height = self.screen.get_size()
        return 0, HEADER_HEIGHT, max(1, width - SIDEBAR_WIDTH), max(1, height - HEADER_HEIGHT)

    def _tile_size(self) -> int:
        mx, my, mw, mh = self._map_area()
        world = self.engine.world
        return max(4, min(mw // world.size, mh // world.size))

    def _map_origin(self) -> tuple[int, int]:
        mx, my, mw, mh = self._map_area()
        world = self.engine.world
        tile = self._tile_size()
        ox = mx + (mw - tile * world.size) // 2
        oy = my + (mh - tile * world.size) // 2
        return ox, oy

    def _tile_rect(self, x: int, y: int) -> pygame.Rect:
        ox, oy = self._map_origin()
        tile = self._tile_size()
        return pygame.Rect(ox + x * tile, oy + y * tile, tile, tile)

    def _agent_center(self, agent: AgentState) -> tuple[int, int]:
        rect = self._tile_rect(agent.position[0], agent.position[1])
        return rect.center

    def _agent_at(self, position: tuple[int, int]) -> AgentState | None:
        px, py = position
        best: AgentState | None = None
        best_distance = None
        for agent in self.engine.world.agents.values():
            cx, cy = self._agent_center(agent)
            distance = abs(cx - px) + abs(cy - py)
            if best_distance is None or distance < best_distance:
                best = agent
                best_distance = distance
        if best is None or best_distance is None:
            return None
        reach = max(self._tile_size(), 14)
        return best if best_distance <= reach else None

    def _inspector_view_height(self) -> int:
        return self.screen.get_height() - HEADER_HEIGHT

    # -------------------------------------------------------------- drawing

    def render_frame(self) -> None:
        self.screen.fill(HUD_COLOR)
        self._draw_map()
        self._draw_agents()
        self._draw_header()
        self._draw_sidebar()
        pygame.display.flip()

    def _draw_map(self) -> None:
        world = self.engine.world
        for y in range(world.size):
            for x in range(world.size):
                tile = world.grid[y][x]
                rect = self._tile_rect(x, y)
                color = TILE_COLORS.get(tile.kind, TILE_COLORS["grass"])
                pygame.draw.rect(self.screen, color, rect)
                if tile.kind == "farm":
                    overlay = CROP_OVERLAYS.get(tile.crop_stage)
                    if overlay and overlay[3] > 0:
                        surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                        surface.fill(overlay)
                        self.screen.blit(surface, rect.topleft)
                elif tile.kind == "forest" and tile.wood > 0 and self._tile_size() >= 14:
                    label = self.small_font.render(str(tile.wood), True, (220, 240, 220))
                    self.screen.blit(label, label.get_rect(center=rect.center))
                elif tile.kind == "house" and tile.house_owner and self._tile_size() >= 16:
                    pygame.draw.rect(self.screen, (60, 40, 26), rect, 1)

        for name, position in world.landmarks.items():
            if name.endswith("_site"):
                self._draw_site_label(position, SITE_LABELS.get(name, name.upper()))

        night_alpha = self._night_alpha()
        if night_alpha > 0:
            mx, my, mw, mh = self._map_area()
            surface = pygame.Surface((mw, mh), pygame.SRCALPHA)
            surface.fill((10, 14, 40, night_alpha))
            self.screen.blit(surface, (mx, my))

    def _draw_site_label(self, position: tuple[int, int], label: str) -> None:
        if not label:
            return
        rect = self._tile_rect(position[0], position[1])
        pygame.draw.rect(self.screen, ACCENT_COLOR, rect, 1)
        if self._tile_size() >= 18:
            text = self.small_font.render(label, True, ACCENT_COLOR)
            self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_agents(self) -> None:
        tile = self._tile_size()
        radius = max(4, tile // 2 - 1)
        for agent in self.engine.world.agents.values():
            cx, cy = self._agent_center(agent)
            if self.selected_agent == agent.name:
                pygame.draw.circle(self.screen, ACCENT_COLOR, (cx, cy), radius + 3, 2)
            pygame.draw.circle(self.screen, (20, 20, 24), (cx, cy), radius + 1)
            pygame.draw.circle(self.screen, agent.sprite_color, (cx, cy), radius)
            if agent.is_sleeping and tile >= 12:
                label = self.small_font.render("z", True, (255, 255, 255))
                self.screen.blit(label, (cx + radius - 2, cy - radius - 10))

            if tile >= 14:
                name = self.small_font.render(agent.name, True, TEXT_COLOR)
                self.screen.blit(name, name.get_rect(midbottom=(cx, cy - radius - 2)))

                energy_width = tile - 2
                pygame.draw.rect(
                    self.screen,
                    (40, 40, 46),
                    pygame.Rect(cx - energy_width // 2, cy + radius + 2, energy_width, 3),
                )
                pygame.draw.rect(
                    self.screen,
                    (120, 220, 120) if agent.energy > 0.4 else (220, 120, 90),
                    pygame.Rect(
                        cx - energy_width // 2,
                        cy + radius + 2,
                        int(energy_width * _clamp(agent.energy, 0.0, 1.0)),
                        3,
                    ),
                )

            if agent.speech_bubble and tile >= 12:
                self._draw_speech_bubble(agent)

    def _draw_speech_bubble(self, agent: AgentState) -> None:
        cx, cy = self._agent_center(agent)
        text = agent.speech_bubble
        if len(text) > 42:
            text = text[:39] + "..."
        surface = self.small_font.render(text, True, (24, 24, 30))
        pad = 4
        box = pygame.Rect(0, 0, surface.get_width() + pad * 2, surface.get_height() + pad * 2)
        box.midbottom = (cx, cy - self._tile_size() - 6)
        box.clamp_ip(self.screen.get_rect())
        pygame.draw.rect(self.screen, (245, 245, 240), box, border_radius=6)
        pygame.draw.rect(self.screen, (90, 90, 100), box, 1, border_radius=6)
        self.screen.blit(surface, surface.get_rect(center=box.center))

    def _draw_header(self) -> None:
        world = self.engine.world
        width = self.screen.get_width()
        pygame.draw.rect(self.screen, (16, 18, 24), pygame.Rect(0, 0, width, HEADER_HEIGHT))
        hour = int(world.time_of_day * 24)
        minute = int((world.time_of_day * 24 - hour) * 60)
        title = self.title_font.render(
            f"Village Sim   Day {world.day}  {hour:02d}:{minute:02d}  tick {world.tick_count}",
            True,
            TEXT_COLOR,
        )
        self.screen.blit(title, (14, 8))

        chips: list[str] = []
        if world.is_market_active():
            chips.append("MARKET HOUR")
        if self.paused:
            chips.append("PAUSED (SPACE)")
        if self.engine.world.pending_trades:
            pending = sum(1 for t in self.engine.world.pending_trades.values() if t.status == "pending")
            if pending:
                chips.append(f"TRADES PENDING: {pending}")
        x = 14
        y = 34
        for chip in chips:
            surface = self.small_font.render(chip, True, (30, 26, 12))
            rect = surface.get_rect(topleft=(x, y))
            rect = rect.inflate(10, 4)
            pygame.draw.rect(self.screen, ACCENT_COLOR, rect, border_radius=4)
            self.screen.blit(surface, (x + 5, y + 2))
            x += rect.width + 8

    def _draw_sidebar(self) -> None:
        width, height = self.screen.get_size()
        sidebar_rect = pygame.Rect(width - SIDEBAR_WIDTH, HEADER_HEIGHT, SIDEBAR_WIDTH, height - HEADER_HEIGHT)
        pygame.draw.rect(self.screen, SIDEBAR_COLOR, sidebar_rect)
        pygame.draw.line(self.screen, (50, 52, 62), (sidebar_rect.left, sidebar_rect.top), (sidebar_rect.left, sidebar_rect.bottom), 2)

        lines: list[tuple[str, pygame.Color | tuple[int, int, int], int]] = []
        lines.extend(self._village_lines())
        lines.append(("", TEXT_COLOR, 8))
        lines.extend(self._project_lines())
        lines.append(("", TEXT_COLOR, 8))
        if self.selected_agent:
            lines.extend(self._agent_lines(self.selected_agent))
        else:
            hint = self.font.render("Click a villager to inspect them", True, MUTED_COLOR)
            self.screen.blit(hint, (sidebar_rect.left + 12, sidebar_rect.top + 10))

        # Manual layout pass: measure, clamp scroll, then draw.
        content_height = sum(line_height for _, _, line_height in lines)
        self._inspector_content_height = content_height
        self.inspector_scroll = int(
            _clamp(self.inspector_scroll, 0, max(0, content_height - self._inspector_view_height()))
        )

        clip = sidebar_rect.copy()
        clip.top += 8
        clip.height -= 16
        y_offset = sidebar_rect.top + 8 - self.inspector_scroll
        max_x = sidebar_rect.right - 10
        for text, color, line_height in lines:
            target_rect = pygame.Rect(sidebar_rect.left + 12, y_offset, SIDEBAR_WIDTH - 24, line_height)
            if target_rect.bottom >= clip.top and target_rect.top <= clip.bottom and text:
                for wrapped in self._wrap_text(text, self.font, SIDEBAR_WIDTH - 28):
                    surface = self.font.render(wrapped, True, color)
                    if surface.get_width() > max_x - sidebar_rect.left - 12:
                        surface = pygame.transform.smoothscale(
                            surface, (max_x - sidebar_rect.left - 12, surface.get_height())
                        )
                    self.screen.blit(surface, (sidebar_rect.left + 12, y_offset))
                    y_offset += surface.get_height() + 1
            else:
                for wrapped in self._wrap_text(text, self.font, SIDEBAR_WIDTH - 28):
                    y_offset += self.font.size(wrapped)[1] + 1
            y_offset += 2

    def _village_lines(self) -> list[tuple[str, tuple[int, int, int], int]]:
        world = self.engine.world
        lines = [(f"Village state", ACCENT_COLOR, 24)]
        lines.append((f"Food    {world.village_food:5.1f} / 12   {'#' * int(world.village_food)}", TEXT_COLOR, 20))
        lines.append((f"Warmth  {world.village_warmth:5.1f} / 12   {'#' * int(world.village_warmth)}", TEXT_COLOR, 20))
        lines.append((f"Morale  {world.village_morale:5.1f} / 12   {'#' * int(world.village_morale)}", TEXT_COLOR, 20))
        agents = ", ".join(world.agents.keys())
        lines.append((f"Villagers: {agents}", MUTED_COLOR, 20))
        return lines

    def _project_lines(self) -> list[tuple[str, tuple[int, int, int], int]]:
        lines = [("Public projects", ACCENT_COLOR, 24)]
        for project in self.engine.world.public_projects.values():
            if project.completed:
                lines.append((f"{project.title}: completed", (140, 220, 140), 20))
            else:
                remaining = ", ".join(f"{item}:{amount}" for item, amount in project.remaining().items() if amount > 0)
                lines.append((f"{project.title}: needs {remaining}", TEXT_COLOR, 20))
        return lines

    def _agent_lines(self, name: str) -> list[tuple[str, tuple[int, int, int], int]]:
        world = self.engine.world
        agent = world.agents.get(name)
        if agent is None:
            self.selected_agent = None
            return []
        lines = [(f"{name} (click map to deselect)", ACCENT_COLOR, 26)]
        lines.append((f"Action: {agent.current_action}", TEXT_COLOR, 20))
        lines.append((f"Position: {agent.position}   House: {agent.house_position}", TEXT_COLOR, 20))
        lines.append((f"Energy: {agent.energy:.2f}{'  (sleeping)' if agent.is_sleeping else ''}", TEXT_COLOR, 20))
        inventory = ", ".join(f"{item} x{amount}" for item, amount in sorted(agent.inventory.items())) or "empty"
        lines.append((f"Inventory: {inventory}", TEXT_COLOR, 20))
        lines.append((f"Thought: {agent.last_thought or 'none yet'}", (180, 200, 240), 20))
        if agent.pending_result:
            lines.append((f"Last result: {agent.pending_result}", MUTED_COLOR, 20))
        memory_lines = self.engine.memory_store.get(name).recall_lines(limit=3)
        if memory_lines:
            lines.append(("Recent memories:", ACCENT_COLOR, 22))
            lines.extend((f"- {item}", MUTED_COLOR, 20) for item in memory_lines)
        relationship_lines = self.engine.relationships.summary_for(name)
        if relationship_lines:
            lines.append(("Relationships:", ACCENT_COLOR, 22))
            lines.extend((f"- {item}", MUTED_COLOR, 20) for item in relationship_lines)
        return lines

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        if not text:
            return [""]
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if font.size(trial)[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _night_alpha(self) -> int:
        time_of_day = self.engine.world.time_of_day
        if time_of_day <= 0.25 or time_of_day >= 0.8:
            return 80
        if time_of_day <= 0.35:
            return int(80 * (0.35 - time_of_day) / 0.10)
        if time_of_day >= 0.7:
            return int(80 * (time_of_day - 0.7) / 0.10)
        return 0
