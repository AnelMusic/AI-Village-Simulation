from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
from typing import Any

from .config import AppConfig


TileKind = str
CropStage = str


@dataclass
class Tile:
    kind: TileKind = "grass"
    passable: bool = True
    house_owner: str | None = None
    feature: str | None = None
    road: bool = False
    wood: int = 0
    berries: int = 0
    fish: int = 0
    flowers: int = 0
    crop_stage: CropStage = "empty"
    crop_progress: float = 0.0
    crop_owner: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tile":
        return cls(**data)


@dataclass
class AgentState:
    name: str
    position: tuple[int, int]
    house_position: tuple[int, int]
    sprite_color: tuple[int, int, int]
    inventory: dict[str, int] = field(default_factory=dict)
    energy: float = 1.0
    is_sleeping: bool = False
    current_action: str = "idle"
    speech_bubble: str | None = None
    speech_bubble_ttl: float = 0.0
    last_thought: str = ""
    last_observation: str = ""
    current_path: list[tuple[int, int]] = field(default_factory=list)
    move_target_label: str | None = None
    next_think_tick: int = 0
    pending_result: str | None = None
    last_tool: str | None = None
    last_social_tick: int = 0
    comfort_ticks: int = 0
    last_action_signature: str = ""
    repeated_action_count: int = 0
    repeated_tool_count: int = 0
    house_fire_ticks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "position": list(self.position),
            "house_position": list(self.house_position),
            "sprite_color": list(self.sprite_color),
            "inventory": dict(self.inventory),
            "energy": self.energy,
            "is_sleeping": self.is_sleeping,
            "current_action": self.current_action,
            "speech_bubble": self.speech_bubble,
            "speech_bubble_ttl": self.speech_bubble_ttl,
            "last_thought": self.last_thought,
            "last_observation": self.last_observation,
            "current_path": [list(item) for item in self.current_path],
            "move_target_label": self.move_target_label,
            "next_think_tick": self.next_think_tick,
            "pending_result": self.pending_result,
            "last_tool": self.last_tool,
            "last_social_tick": self.last_social_tick,
            "comfort_ticks": self.comfort_ticks,
            "last_action_signature": self.last_action_signature,
            "repeated_action_count": self.repeated_action_count,
            "repeated_tool_count": self.repeated_tool_count,
            "house_fire_ticks": self.house_fire_ticks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentState":
        current_path = [tuple(item) for item in data.get("current_path", [])]
        return cls(
            name=data["name"],
            position=tuple(data["position"]),
            house_position=tuple(data["house_position"]),
            sprite_color=tuple(data["sprite_color"]),
            inventory=dict(data.get("inventory", {})),
            energy=float(data.get("energy", 1.0)),
            is_sleeping=bool(data.get("is_sleeping", False)),
            current_action=data.get("current_action", "idle"),
            speech_bubble=data.get("speech_bubble"),
            speech_bubble_ttl=float(data.get("speech_bubble_ttl", 0.0)),
            last_thought=data.get("last_thought", ""),
            last_observation=data.get("last_observation", ""),
            current_path=current_path,
            move_target_label=data.get("move_target_label"),
            next_think_tick=int(data.get("next_think_tick", 0)),
            pending_result=data.get("pending_result"),
            last_tool=data.get("last_tool"),
            last_social_tick=int(data.get("last_social_tick", 0)),
            comfort_ticks=int(data.get("comfort_ticks", 0)),
            last_action_signature=data.get("last_action_signature", ""),
            repeated_action_count=int(data.get("repeated_action_count", 0)),
            repeated_tool_count=int(data.get("repeated_tool_count", 0)),
            house_fire_ticks=int(data.get("house_fire_ticks", 0)),
        )


@dataclass
class TradeOffer:
    trade_id: str
    from_agent: str
    to_agent: str
    offer: dict[str, int]
    request: dict[str, int]
    message: str
    created_tick: int
    expires_tick: int
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradeOffer":
        return cls(**data)


@dataclass
class AllianceOffer:
    proposal_id: str
    from_agent: str
    to_agent: str
    message: str
    created_tick: int
    expires_tick: int
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AllianceOffer":
        return cls(**data)


@dataclass
class WorldEvent:
    tick: int
    day: int
    time_of_day: float
    kind: str
    actor: str
    summary: str
    location: tuple[int, int] | None = None
    target: str | None = None
    public: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.location is not None:
            data["location"] = list(self.location)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldEvent":
        location = data.get("location")
        return cls(
            tick=int(data["tick"]),
            day=int(data["day"]),
            time_of_day=float(data["time_of_day"]),
            kind=data["kind"],
            actor=data["actor"],
            summary=data["summary"],
            location=tuple(location) if location is not None else None,
            target=data.get("target"),
            public=bool(data.get("public", True)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ProjectState:
    name: str
    title: str
    site: tuple[int, int]
    required: dict[str, int]
    progress: dict[str, int]
    description: str
    bonus_description: str
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["site"] = list(self.site)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        return cls(
            name=data["name"],
            title=data["title"],
            site=tuple(data["site"]),
            required=dict(data["required"]),
            progress=dict(data["progress"]),
            description=data["description"],
            bonus_description=data["bonus_description"],
            completed=bool(data.get("completed", False)),
        )

    def remaining(self) -> dict[str, int]:
        return {item: max(0, self.required.get(item, 0) - self.progress.get(item, 0)) for item in self.required}

    def summary(self) -> str:
        remain = self.remaining()
        remain_text = ", ".join(f"{item}:{amount}" for item, amount in remain.items())
        status = "completed" if self.completed else f"needs {remain_text}"
        return f"{self.title} at {self.site}: {status}"


@dataclass
class WorldState:
    size: int
    grid: list[list[Tile]]
    agents: dict[str, AgentState]
    landmarks: dict[str, tuple[int, int]] = field(default_factory=dict)
    public_projects: dict[str, ProjectState] = field(default_factory=dict)
    schema_version: int = 7
    village_food: float = 7.0
    village_warmth: float = 6.0
    village_morale: float = 6.0
    market_active_until_tick: int = 0
    tick_count: int = 0
    day: int = 1
    time_of_day: float = 0.25
    pending_trades: dict[str, TradeOffer] = field(default_factory=dict)
    pending_alliances: dict[str, AllianceOffer] = field(default_factory=dict)
    recent_events: list[WorldEvent] = field(default_factory=list)

    def tile_at(self, position: tuple[int, int]) -> Tile:
        x, y = position
        return self.grid[y][x]

    def in_bounds(self, position: tuple[int, int]) -> bool:
        x, y = position
        return 0 <= x < self.size and 0 <= y < self.size

    def neighbors(self, position: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = position
        items = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [item for item in items if self.in_bounds(item)]

    def is_passable(self, position: tuple[int, int]) -> bool:
        return self.in_bounds(position) and self.tile_at(position).passable

    def is_adjacent(self, first: tuple[int, int], second: tuple[int, int]) -> bool:
        return abs(first[0] - second[0]) + abs(first[1] - second[1]) == 1

    def is_market_active(self) -> bool:
        return self.tick_count <= self.market_active_until_tick

    def project_summary_lines(self) -> list[str]:
        return [project.summary() for project in self.public_projects.values()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "schema_version": self.schema_version,
            "tick_count": self.tick_count,
            "day": self.day,
            "time_of_day": self.time_of_day,
            "village_food": self.village_food,
            "village_warmth": self.village_warmth,
            "village_morale": self.village_morale,
            "market_active_until_tick": self.market_active_until_tick,
            "grid": [[tile.to_dict() for tile in row] for row in self.grid],
            "agents": {name: agent.to_dict() for name, agent in self.agents.items()},
            "landmarks": {name: list(position) for name, position in self.landmarks.items()},
            "public_projects": {name: project.to_dict() for name, project in self.public_projects.items()},
            "pending_trades": {trade_id: trade.to_dict() for trade_id, trade in self.pending_trades.items()},
            "pending_alliances": {proposal_id: offer.to_dict() for proposal_id, offer in self.pending_alliances.items()},
            "recent_events": [event.to_dict() for event in self.recent_events[-200:]],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldState":
        grid = [[Tile.from_dict(tile) for tile in row] for row in data["grid"]]
        agents = {name: AgentState.from_dict(agent) for name, agent in data["agents"].items()}
        pending_trades = {
            trade_id: TradeOffer.from_dict(trade) for trade_id, trade in data.get("pending_trades", {}).items()
        }
        pending_alliances = {
            proposal_id: AllianceOffer.from_dict(offer) for proposal_id, offer in data.get("pending_alliances", {}).items()
        }
        recent_events = [WorldEvent.from_dict(event) for event in data.get("recent_events", [])]
        landmarks = {name: tuple(position) for name, position in data.get("landmarks", {}).items()}
        public_projects = {
            name: ProjectState.from_dict(project) for name, project in data.get("public_projects", {}).items()
        }
        return cls(
            size=int(data["size"]),
            grid=grid,
            agents=agents,
            landmarks=landmarks,
            public_projects=public_projects,
            schema_version=int(data.get("schema_version", 1)),
            village_food=float(data.get("village_food", 7.0)),
            village_warmth=float(data.get("village_warmth", 6.0)),
            village_morale=float(data.get("village_morale", 6.0)),
            market_active_until_tick=int(data.get("market_active_until_tick", 0)),
            tick_count=int(data.get("tick_count", 0)),
            day=int(data.get("day", 1)),
            time_of_day=float(data.get("time_of_day", 0.25)),
            pending_trades=pending_trades,
            pending_alliances=pending_alliances,
            recent_events=recent_events,
        )

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "WorldState":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def generate_world(config: AppConfig) -> WorldState:
    size = config.world_size
    grid = [[Tile() for _ in range(size)] for _ in range(size)]

    def set_road_line(start: tuple[int, int], end: tuple[int, int]) -> None:
        x1, y1 = start
        x2, y2 = end
        for x in range(min(x1, x2), max(x1, x2) + 1):
            if grid[y1][x].kind != "house":
                grid[y1][x].road = True
                grid[y1][x].kind = "road"
        for y in range(min(y1, y2), max(y1, y2) + 1):
            if grid[y][x2].kind != "house":
                grid[y][x2].road = True
                grid[y][x2].kind = "road"

    center = (size // 2, size // 2)

    def set_feature(position: tuple[int, int], feature: str, kind: str | None = None, passable: bool = True) -> None:
        x, y = position
        tile = grid[y][x]
        tile.feature = feature
        if kind is not None:
            tile.kind = kind
        tile.passable = passable

    for y in range(center[1] - 2, center[1] + 3):
        for x in range(center[0] - 2, center[0] + 3):
            grid[y][x].road = True
            grid[y][x].kind = "road"
    set_feature(center, "well", kind="well")
    set_feature((center[0] - 1, center[1] - 2), "hearth", kind="hearth")
    set_feature((center[0] - 2, center[1] - 2), "hearth_seat", kind="road")
    set_feature((center[0], center[1] - 2), "hearth_seat", kind="road")
    set_feature((center[0] + 2, center[1] - 1), "notice_board", kind="notice_board")
    set_feature((center[0] + 1, center[1] - 2), "market_stall_frame", kind="road")
    set_feature((center[0] + 2, center[1] - 2), "market_stall_frame", kind="road")
    set_feature((center[0] + 1, center[1] - 3), "market_stall_frame", kind="road")
    set_feature((center[0] + 2, center[1] - 3), "market_stall_frame", kind="road")

    for x in range(1, size - 1):
        grid[center[1]][x].road = True
        grid[center[1]][x].kind = "road"
    for y in range(1, size - 1):
        grid[y][center[0]].road = True
        grid[y][center[0]].kind = "road"

    forest_ranges = [
        (2, center[1] - 4, 4, center[1] + 4),
        (size - 5, center[1] - 4, size - 3, center[1] + 4),
        (center[0] - 3, 2, center[0] + 3, 4),
    ]
    for x1, y1, x2, y2 in forest_ranges:
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                grid[y][x].kind = "forest"
                grid[y][x].wood = 8

    for y in range(size - 7, size - 3):
        for x in range(center[0] - 3, center[0] + 4):
            grid[y][x].kind = "berry_grove"
            grid[y][x].berries = 5
            grid[y][x].feature = "berry_bush"

    pond_left = size - 8
    pond_top = center[1] - 3
    for y in range(pond_top, pond_top + 5):
        for x in range(pond_left, pond_left + 5):
            if abs(x - (pond_left + 2)) + abs(y - (pond_top + 2)) <= 4:
                grid[y][x].kind = "water"
                grid[y][x].fish = 4
                grid[y][x].feature = "pond"
                grid[y][x].passable = True
    set_feature((pond_left - 1, pond_top + 2), "dock", kind="road")
    set_feature((pond_left, pond_top + 2), "dock", kind="water")

    flower_left = 2
    flower_top = size - 8
    for y in range(flower_top, flower_top + 4):
        for x in range(flower_left, flower_left + 5):
            grid[y][x].kind = "flower_garden"
            grid[y][x].flowers = 5
            grid[y][x].feature = "flower_patch"

    for y in range(center[1] - 1, center[1] + 2):
        for x in range(center[0] - 3, center[0] + 4):
            if abs(x - center[0]) <= 1 and abs(y - center[1]) <= 1:
                continue
            if grid[y][x].kind in {"hearth", "notice_board"}:
                continue
            tile = grid[y][x]
            tile.kind = "farm"
            tile.crop_owner = None
            distance = abs(x - center[0]) + abs(y - center[1])
            if distance % 3 == 0:
                tile.crop_stage = "ripe"
                tile.crop_progress = 1.0
            elif distance % 2 == 0:
                tile.crop_stage = "growing"
                tile.crop_progress = 0.6
            else:
                tile.crop_stage = "empty"
                tile.crop_progress = 0.0

    inventory_items = ("wood", "wheat", "berries", "fish", "flowers", "meal")

    agents: dict[str, AgentState] = {}
    for character in config.characters:
        hx, hy = character.house_position
        grid[hy][hx].kind = "house"
        grid[hy][hx].house_owner = character.name
        grid[hy][hx].passable = True
        set_road_line(character.house_position, center)
        starting_inventory = {item: 10 for item in inventory_items}
        for item, quantity in character.starting_inventory.items():
            starting_inventory[item] = starting_inventory.get(item, 10) + quantity
        agents[character.name] = AgentState(
            name=character.name,
            position=character.house_position,
            house_position=character.house_position,
            sprite_color=character.sprite_color,
            inventory=starting_inventory,
        )

    landmarks = {
        "village_plaza": center,
        "well": center,
        "community_hearth": (center[0] - 1, center[1] - 2),
        "notice_board": (center[0] + 2, center[1] - 1),
        "communal_farm": (center[0] - 3, center[1]),
        "west_forest": (3, center[1]),
        "east_forest": (size - 4, center[1]),
        "north_forest": (center[0], 3),
        "berry_grove": (center[0], size - 5),
        "village_pond": (pond_left + 2, pond_top + 2),
        "flower_garden": (flower_left + 2, flower_top + 1),
        "granary_site": (center[0] - 2, center[1] + 2),
        "wood_shed_site": (center[0] + 2, center[1] + 2),
        "market_stalls_site": (center[0] + 2, center[1] - 2),
        "bathhouse_site": (center[0] - 3, center[1] - 2),
        "greenhouse_site": (center[0] - 1, center[1] + 4),
    }
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        set_feature((landmarks["granary_site"][0] + dx, landmarks["granary_site"][1] + dy), "granary_site", kind="grass")
    for dx, dy in ((0, 0), (-1, 0), (0, 1), (-1, 1)):
        set_feature((landmarks["wood_shed_site"][0] + dx, landmarks["wood_shed_site"][1] + dy), "wood_shed_site", kind="grass")
    for dx, dy in ((0, 0), (-1, 0), (0, -1), (-1, -1)):
        set_feature((landmarks["market_stalls_site"][0] + dx, landmarks["market_stalls_site"][1] + dy), "market_site", kind="road")
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        set_feature((landmarks["bathhouse_site"][0] + dx, landmarks["bathhouse_site"][1] + dy), "bathhouse_site", kind="road")
    for dx, dy in ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)):
        set_feature((landmarks["greenhouse_site"][0] + dx, landmarks["greenhouse_site"][1] + dy), "greenhouse_site", kind="grass")

    public_projects = {
        "granary": ProjectState(
            name="granary",
            title="Granary",
            site=landmarks["granary_site"],
            required={"wood": 6, "wheat": 10},
            progress={"wood": 0, "wheat": 0},
            description="A communal granary that protects food stores and keeps harvests useful for longer.",
            bonus_description="Food drains slower and communal harvests become more productive.",
        ),
        "wood_shed": ProjectState(
            name="wood_shed",
            title="Wood Shed",
            site=landmarks["wood_shed_site"],
            required={"wood": 12, "wheat": 4},
            progress={"wood": 0, "wheat": 0},
            description="A shared wood shed that keeps warmth steady and makes rest more effective.",
            bonus_description="Warmth drains slower and resting recovers more energy.",
        ),
        "market_stalls": ProjectState(
            name="market_stalls",
            title="Market Stalls",
            site=landmarks["market_stalls_site"],
            required={"wood": 8, "wheat": 6},
            progress={"wood": 0, "wheat": 0},
            description="A proper market square with stalls, shade, and gathering space for trade and gossip.",
            bonus_description="Market hours last longer and plaza interactions become more rewarding.",
        ),
        "bathhouse": ProjectState(
            name="bathhouse",
            title="Bathhouse",
            site=landmarks["bathhouse_site"],
            required={"wood": 10, "wheat": 5},
            progress={"wood": 0, "wheat": 0},
            description="A warm communal bathhouse by the well that turns the center into a better place to recover and linger.",
            bonus_description="Resting near the well and plaza becomes stronger, and shared recovery boosts morale.",
        ),
        "greenhouse": ProjectState(
            name="greenhouse",
            title="Greenhouse",
            site=landmarks["greenhouse_site"],
            required={"wood": 12, "wheat": 8},
            progress={"wood": 0, "wheat": 0},
            description="A glassy community greenhouse that keeps crops and flowers thriving around the village center.",
            bonus_description="Farms ripen faster, flower gardens regrow faster, and cooking ingredients stay more available.",
        ),
    }
    return WorldState(
        size=size,
        grid=grid,
        agents=agents,
        landmarks=landmarks,
        public_projects=public_projects,
        schema_version=7,
        village_food=5.8,
        village_warmth=5.4,
        village_morale=6.4,
        market_active_until_tick=6,
    )
