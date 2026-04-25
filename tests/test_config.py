from __future__ import annotations

from pathlib import Path

from sim.config import load_config


def test_config_loads_defaults_and_env_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
openai_key: null
characters:
  - name: Mira
    sprite_color: [220, 120, 80]
    house_position: [4, 4]
    personality: Farmer
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.openai_key == "test-key"
    assert config.world_size == 24
    assert config.ticks_per_second == 0.5
    assert config.characters[0].name == "Mira"
