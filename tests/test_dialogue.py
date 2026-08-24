from __future__ import annotations

from sim.agent import build_observation
from sim.engine import SimulationEngine


def place_adjacent(engine: SimulationEngine):
    mira = engine.world.agents["Mira"]
    fen = engine.world.agents["Fen"]
    mira.position = (5, 5)
    fen.position = (6, 5)
    return mira, fen


def test_direct_speech_opens_conversation_awaiting_listener(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        result = engine.action_resolver.apply(
            mira,
            "speak",
            {"message": "Fen, do you have spare wheat?", "target": "Fen", "thought": "Ask Fen."},
        )
        assert result.success
        conversations = list(engine.world.conversations.values())
        assert len(conversations) == 1
        conversation = conversations[0]
        assert conversation.awaiting == "Fen"
        assert conversation.last_speaker == "Mira"
        assert fen.interrupt_flag

        observation = build_observation(app_config, engine.world, fen, engine.memory_store, engine.relationships)
        assert "(reply expected)" in observation
        assert conversation.conversation_id in observation
    finally:
        engine.shutdown()


def test_reply_flips_conversation_and_builds_trust(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        engine.action_resolver.apply(
            mira, "speak", {"message": "Trade later?", "target": "Fen", "thought": "Talk."}
        )
        conversation = next(iter(engine.world.conversations.values()))
        trust_before = engine.relationships.get("Fen", "Mira").trust

        result = engine.action_resolver.apply(
            fen,
            "reply",
            {"conversation_id": conversation.conversation_id, "message": "Sure, meet me at market.", "thought": "Agree."},
        )
        assert result.success
        assert conversation.awaiting == "Mira"
        assert conversation.last_speaker == "Fen"
        assert engine.relationships.get("Fen", "Mira").trust > trust_before
        assert mira.interrupt_flag
    finally:
        engine.shutdown()


def test_ask_help_accept_spends_owed_favor(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        fen.inventory["wood"] = 5
        # Fen owes Mira a favor (Fen received a gift earlier).
        engine.relationships.record_gift("Mira", "Fen", 1, "earlier gift", favor_delta=0.8)
        assert engine.relationships.get("Fen", "Mira").favor >= 0.5

        ask = engine.action_resolver.apply(
            mira,
            "ask_help",
            {"target_agent": "Fen", "item": "wood", "quantity": 2, "message": "I need wood for the shed.", "thought": "Call it in."},
        )
        assert ask.success
        assert fen.interrupt_flag
        ask_id = next(iter(engine.world.pending_asks.keys()))

        favor_before = engine.relationships.get("Fen", "Mira").favor
        accept = engine.action_resolver.apply(fen, "accept_help", {"ask_id": ask_id, "thought": "I owe her."})
        assert accept.success
        assert mira.inventory["wood"] == 3  # 1 starting wood + 2 received
        assert fen.inventory["wood"] == 3
        assert engine.relationships.get("Fen", "Mira").favor < favor_before
    finally:
        engine.shutdown()


def test_ask_help_accept_without_favor_creates_obligation(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        fen.inventory["wheat"] = 4
        ask = engine.action_resolver.apply(
            mira, "ask_help", {"target_agent": "Fen", "item": "wheat", "quantity": 1, "message": "Please?", "thought": "Beg."}
        )
        ask_id = next(iter(engine.world.pending_asks.keys()))
        accept = engine.action_resolver.apply(fen, "accept_help", {"ask_id": ask_id, "thought": "Fine."})
        assert accept.success
        # Mira now owes Fen for the help.
        assert engine.relationships.get("Mira", "Fen").favor > 0
    finally:
        engine.shutdown()


def test_reject_help_with_item_cools_relationship(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        fen.inventory["wood"] = 5
        engine.action_resolver.apply(
            mira, "ask_help", {"target_agent": "Fen", "item": "wood", "quantity": 1, "message": "Please?", "thought": "Ask."}
        )
        ask_id = next(iter(engine.world.pending_asks.keys()))
        trust_before = engine.relationships.get("Fen", "Mira").trust
        reject = engine.action_resolver.apply(
            fen, "reject_help", {"ask_id": ask_id, "reason": "Saving it.", "thought": "No."}
        )
        assert reject.success
        assert engine.relationships.get("Fen", "Mira").trust < trust_before
    finally:
        engine.shutdown()


def test_counter_offer_replaces_trade_and_can_be_accepted(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        mira.inventory["wood"] = 3
        fen.inventory["wheat"] = 3
        offer = engine.action_resolver.apply(
            mira,
            "offer_trade",
            {
                "target_agent": "Fen",
                "offer": {"wood": 1, "wheat": 0, "berries": 0, "fish": 0, "flowers": 0, "meal": 0},
                "request": {"wood": 0, "wheat": 2, "berries": 0, "fish": 0, "flowers": 0, "meal": 0},
                "message": "Wood for wheat?",
                "thought": "Trade.",
            },
        )
        assert offer.success
        original_id = next(iter(engine.world.pending_trades.keys()))

        full_offer = {"wood": 0, "wheat": 1, "berries": 0, "fish": 0, "flowers": 0, "meal": 0}
        full_request = {"wood": 1, "wheat": 0, "berries": 0, "fish": 0, "flowers": 0, "meal": 0}
        counter = engine.action_resolver.apply(
            fen,
            "counter_offer",
            {
                "trade_id": original_id,
                "offer": full_offer,
                "request": full_request,
                "message": "One wheat for one wood, final offer.",
                "thought": "Haggle.",
            },
        )
        assert counter.success
        assert engine.world.pending_trades[original_id].status == "countered"
        counter_id = next(
            trade_id
            for trade_id, trade in engine.world.pending_trades.items()
            if trade.status == "pending" and trade.from_agent == "Fen"
        )
        assert mira.interrupt_flag

        accepted = engine.action_resolver.apply(mira, "accept_trade", {"trade_id": counter_id, "thought": "Deal."})
        assert accepted.success
        assert mira.inventory["wheat"] >= 1
        assert fen.inventory["wood"] >= 1
    finally:
        engine.shutdown()


def test_conversations_and_asks_expire(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira, fen = place_adjacent(engine)
        engine.action_resolver.apply(mira, "speak", {"message": "Hello?", "target": "Fen", "thought": "Greet."})
        engine.action_resolver.apply(
            fen, "ask_help", {"target_agent": "Mira", "item": "wood", "quantity": 1, "message": "Wood?", "thought": "Ask."}
        )
        conversation = next(iter(engine.world.conversations.values()))
        ask = next(iter(engine.world.pending_asks.values()))
        engine.world.tick_count = max(conversation.expires_tick, ask.expires_tick) + 1

        engine._expire_conversations()
        engine._expire_asks()
        assert not conversation.active
        assert ask.status == "expired"
    finally:
        engine.shutdown()
