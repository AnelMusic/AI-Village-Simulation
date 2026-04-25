from __future__ import annotations

from pathlib import Path

import pytest

from sim.config import AppConfig, CharacterConfig


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    config = AppConfig(
        openai_key=None,
        model="gpt-4.1-mini",
        ticks_per_second=4.0,
        autosave_interval_seconds=1,
        data_dir=str(data_dir),
        logs_dir=str(logs_dir),
        save_file=str(data_dir / "world_state.json"),
        event_log_file=str(logs_dir / "events.csv"),
        characters=[
            CharacterConfig(
                name="Mira",
                sprite_color=(220, 120, 80),
                house_position=(4, 4),
                personality="Farmer",
            ),
            CharacterConfig(
                name="Fen",
                sprite_color=(80, 160, 220),
                house_position=(8, 4),
                personality="Trader",
            ),
        ],
    )
    return config
