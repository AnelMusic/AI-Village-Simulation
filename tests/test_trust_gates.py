from __future__ import annotations

from sim.engine import SimulationEngine


def place_adjacent(engine: SimulationEngine):
    mira = engine.world.agents["Mira"]
    fen = engine.world.agents["Fen"]
    mira.position = (5, 5)
    fen.position = (6, 5)
    return mira, fen


def test_alliance_requires_minimum_trust(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        assert engine.relationships.get("Mira", "Fen").trust < 0.15

        refused = engine.action_resolver.apply(
            mira,
            "propose_alliance",
            {"target_agent": "Fen", "message": "Team up?", "thought": "Ally."},
        )
        assert not refused.success
        assert "trust" in refused.message.lower()
        assert not engine.world.pending_alliances

        engine.relationships.record("Mira", "Fen", engine.world.day, 0.3, "many fair trades")
        accepted_proposal = engine.action_resolver.apply(
            mira,
            "propose_alliance",
            {"target_agent": "Fen", "message": "Team up?", "thought": "Ally."},
        )
        assert accepted_proposal.success
    finally:
        engine.shutdown()


def test_hostile_agents_refuse_gifts_and_trades(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        engine.relationships.record("Mira", "Fen", engine.world.day, -0.5, "broken promises")

        gift = engine.action_resolver.apply(
            mira,
            "give_gift",
            {"target_agent": "Fen", "item": "wheat", "quantity": 1, "message": "No hard feelings?", "thought": "Mend."},
        )
        assert not gift.success
        assert "trust" in gift.message.lower()

        offer = engine.action_resolver.apply(
            mira,
            "offer_trade",
            {
                "target_agent": "Fen",
                "offer": {"wood": 1, "wheat": 0, "berries": 0, "fish": 0, "flowers": 0, "meal": 0},
                "request": {"wood": 0, "wheat": 1, "berries": 0, "fish": 0, "flowers": 0, "meal": 0},
                "message": "Wood?",
                "thought": "Trade.",
            },
        )
        assert offer.success
        trade_id = next(iter(engine.world.pending_trades.keys()))
        # Fen's side is the one gated on Fen's trust in Mira.
        engine.relationships.record("Fen", "Mira", engine.world.day, -0.5, "grudge")
        refused_trade = engine.action_resolver.apply(fen, "accept_trade", {"trade_id": trade_id, "thought": "Hm."})
        assert not refused_trade.success
        assert "trust" in refused_trade.message.lower()
    finally:
        engine.shutdown()


def test_ignoring_conversation_decays_trust(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        engine.action_resolver.apply(mira, "speak", {"message": "Fen, answer me!", "target": "Fen", "thought": "Talk."})
        conversation = next(iter(engine.world.conversations.values()))
        trust_before = engine.relationships.get("Mira", "Fen").trust

        engine.world.tick_count = conversation.expires_tick + 1
        engine._expire_conversations()

        assert not conversation.active
        assert engine.relationships.get("Mira", "Fen").trust < trust_before
    finally:
        engine.shutdown()


def test_trust_decays_toward_neutral_over_idle_days(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        engine.relationships.record("Mira", "Fen", 1, 0.4, "good trade")
        trust_before = engine.relationships.get("Mira", "Fen").trust
        engine.world.day = 4  # idle for days

        engine._decay_relationships()

        trust_after = engine.relationships.get("Mira", "Fen").trust
        assert trust_after < trust_before
        assert trust_after > 0  # drifted toward neutral, not flipped
    finally:
        engine.shutdown()
